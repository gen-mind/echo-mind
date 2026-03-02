# Phase 7: Skills Migration & EchoMind-Native Skills — Execution Plan

> **Status**: Ready for implementation
> **Phase**: 7 of 8 (Master plan: `agent_execution-plan.md`)
> **Prerequisites**: Phases 1-4 complete (MCP Gateway, Connectors, Skills Engine, Sandbox Foundation)
> **Estimated effort**: 1.5–2 weeks

---

## 1. Executive Summary

Phase 7 completes the EchoMind skill ecosystem. The MCP gateway (Phase 1), connector tools (Phase 2), skill engine (Phase 3), and sandbox foundation (Phase 4) are all operational. **42 skills are already loaded** in `config/mcp-gateway/skills/`, with 12 MCP tools registered across search, connectors, skills, and API proxy namespaces.

**What Phase 7 delivers:**

1. **Quality audit & fixes** for all 42 existing skills (correct YAML schema, test coverage, sandbox compatibility)
2. **Upgrade 4 EchoMind-native skills** from documentation-only stubs to fully functional MCP-backed skills
3. **Add missing skills**: `echomind-admin` (system health), `web-scrape` (URL content extraction)
4. **Security framework**: dangerous command detection, per-skill allowlists, sandbox image hardening
5. **Skill testing framework**: unit tests for parser/registry/executor, integration tests for skill execution
6. **Sandbox Docker image updates**: install required binaries for all skills

---

## 2. Current State Audit

### 2.1 MCP Gateway (Operational)

| Component | Status | Files |
|-----------|--------|-------|
| FastMCP server | ✅ Running | `src/mcp_gateway/main.py` |
| Config (Pydantic Settings) | ✅ Complete | `src/mcp_gateway/config.py` |
| Skill registry | ✅ 42 skills loaded | `src/mcp_gateway/skills/registry.py` |
| Skill executor | ✅ Working | `src/mcp_gateway/skills/executor.py` |
| Search backend | ✅ Qdrant + Embedder | `src/mcp_gateway/backends/search_backend.py` |
| Connector backend | ✅ PG + NATS | `src/mcp_gateway/backends/connector_backend.py` |
| API proxy backend | ✅ Google Search | `src/mcp_gateway/backends/api_proxy_backend.py` |
| Audit logger middleware | ✅ Structured JSON | `src/mcp_gateway/middleware/audit_logger.py` |
| Error handler middleware | ✅ Domain → MCP errors | `src/mcp_gateway/middleware/error_handler.py` |

### 2.2 Registered MCP Tools (12 total)

| Namespace | Tool | Description |
|-----------|------|-------------|
| **search** | `search_documents` | Vector similarity search |
| **search** | `list_collections` | List Qdrant collections |
| **search** | `get_collection_info` | Collection statistics |
| **search** | `get_document_chunks` | Retrieve document chunks |
| **skills** | `skills_list` | List all skills |
| **skills** | `skills_get_info` | Get skill documentation |
| **skills** | `skills_execute` | Execute skill command |
| **connectors** | `connectors_list` | List user connectors |
| **connectors** | `connector_status` | Connector sync status |
| **connectors** | `connector_search` | Search within connector |
| **connectors** | `connector_sync` | Trigger manual sync |
| **api** | `web_search` | Google Custom Search |

### 2.3 Skill Inventory (42 loaded)

#### Ported from Moltbot — Direct (27 skills)

| # | Skill | Category | Timeout | Binary Deps |
|---|-------|----------|---------|-------------|
| 1 | `1password` | Security | 30s | `op` |
| 2 | `bird` | Social | 30s | `bird` |
| 3 | `blogwatcher` | Web | 30s | `blogwatcher` |
| 4 | `camsnap` | Media | 30s | `camsnap` |
| 5 | `coding-agent` | Developer | 120s | varies |
| 6 | `discord` | Communication | 30s | config only |
| 7 | `file-edit` | Developer | 30s | `sed`, `awk` |
| 8 | `gemini` | AI | 30s | `gemini` |
| 9 | `gifgrep` | Media | 30s | `gifgrep` |
| 10 | `github` | Developer | 60s | `git`, `gh` |
| 11 | `goplaces` | Web | 30s | `goplaces` |
| 12 | `himalaya` | Communication | 30s | `himalaya` |
| 13 | `mcporter` | Developer | 30s | `mcporter` |
| 14 | `nano-banana-pro` | Media | 30s | `nano-banana-pro` |
| 15 | `nano-pdf` | Media | 30s | `nano-pdf` |
| 16 | `notion` | Productivity | 30s | API only |
| 17 | `obsidian` | Productivity | 30s | `obsidian-cli` |
| 18 | `openai-image-gen` | Media | 30s | `curl` |
| 19 | `openai-whisper` | Media | 30s | `whisper` |
| 20 | `openai-whisper-api` | Media | 30s | `curl` |
| 21 | `oracle` | AI | 30s | `oracle` |
| 22 | `sag` | AI | 30s | `sag` |
| 23 | `skill-creator` | Meta | 30s | none (docs) |
| 24 | `slack` | Communication | 30s | config only |
| 25 | `songsee` | Media | 30s | `songsee` |
| 26 | `summarize` | Web | 30s | `summarize` |
| 27 | `tmux` | Developer | 30s | `tmux` |
| 28 | `trello` | Productivity | 30s | `jq` |
| 29 | `video-frames` | Media | 30s | `ffmpeg` |
| 30 | `weather` | Utility | 15s | `curl` |

#### Adapted from Moltbot (8 skills)

| # | Skill | Adaptation |
|---|-------|-----------|
| 31 | `gog` | Adapted for EchoMind API proxy |
| 32 | `local-places` | Merged with goplaces |
| 33 | `lobster` | Adapted for EchoMind approval workflows |
| 34 | `sherpa-onnx-tts` | Adapted for Docker sandbox |
| 35 | `wacli` | Adapted for container auth |
| 36 | `blucli`* | Listed but not runnable (local network) |
| 37 | `eightctl`* | Listed but not runnable (local network) |
| 38 | `imsg`* | Listed but not runnable (macOS) |

> \* These 3 are in the skills directory but will fail binary checks or platform checks in a Linux sandbox.

#### Replaced Moltbot Skills (3 skills)

| # | Skill | Replaces | New Implementation |
|---|-------|----------|--------------------|
| 39 | `skill-registry` | `clawdhub` | EchoMind skill registry management |
| 40 | `model-usage` | `model-usage` | Points to Langfuse instead of CodexBar |
| 41 | `session-logs` | `session-logs` | Points to EchoMind session API |

#### EchoMind-Native Skills (4 skills — documentation stubs)

| # | Skill | Type | Status |
|---|-------|------|--------|
| 42 | `echomind-search` | Doc-only | ⚠️ Stub — points to MCP tools |
| 43 | `echomind-connectors` | Doc-only | ⚠️ Stub — points to MCP tools |
| 44 | `echomind-documents` | Executable | ✅ curl-based API calls |
| 45 | `echomind-memory` | Executable | ✅ curl-based API calls |

### 2.4 Gap Analysis

| Gap | Impact | Resolution |
|-----|--------|------------|
| `echomind-search` is doc-only stub | Agent can't invoke search via skill | Already available as MCP tools — skill just needs better docs |
| `echomind-connectors` is doc-only stub | Agent can't invoke connectors via skill | Already available as MCP tools — skill just needs better docs |
| No `echomind-admin` skill | Agent can't check system health | Create new skill |
| No `web-scrape` skill | Agent can't extract content from URLs | Create new skill |
| 3 unskippable macOS/LAN skills in registry | Will fail on Linux sandbox | Add platform/binary checks to SKILL.md |
| No unit tests for skills engine | Risk of regression | Create comprehensive test suite |
| No integration tests for skill execution | Can't validate end-to-end flow | Create integration test suite |
| Sandbox image missing many binaries | Skills will fail at runtime | Update Dockerfile |
| No dangerous command detection | Security gap for `coding-agent`, `file-edit` | Add pattern-based detection |

### 2.5 Skipped Skills (16 — documented in `skipped-skills.md`)

| Category | Count | Skills |
|----------|-------|--------|
| macOS-only | 6 | apple-notes, apple-reminders, bear-notes, imsg, peekaboo, things-mac |
| Local hardware/network | 5 | blucli, eightctl, openhue, sonoscli, spotify-player |
| Moltbot-specific | 3 | bluebubbles, canvas, voice-call |
| Personal/non-enterprise | 2 | food-order, ordercli |

These remain deliberately skipped. See `agent_docs/skipped-skills.md` for rationale.

---

## 3. Migration Matrix

Complete status of every skill ever considered for EchoMind:

| # | Skill | Source | Status | Phase 7 Action |
|---|-------|--------|--------|----------------|
| 1 | `1password` | Moltbot | ✅ Ported | Audit & test |
| 2 | `bird` | Moltbot | ✅ Ported | Audit & test |
| 3 | `blogwatcher` | Moltbot | ✅ Ported | Audit & test |
| 4 | `camsnap` | Moltbot | ✅ Adapted | Audit & test |
| 5 | `coding-agent` | Moltbot | ✅ Ported | Add security guardrails |
| 6 | `discord` | Moltbot | ✅ Ported | Audit & test |
| 7 | `file-edit` | Moltbot | ✅ Ported | Add security guardrails |
| 8 | `gemini` | Moltbot | ✅ Ported | Audit & test |
| 9 | `gifgrep` | Moltbot | ✅ Ported | Audit & test |
| 10 | `github` | Moltbot | ✅ Ported | Audit & test |
| 11 | `gog` | Moltbot | ✅ Adapted | Audit & test |
| 12 | `goplaces` | Moltbot | ✅ Ported | Audit & test |
| 13 | `himalaya` | Moltbot | ✅ Ported | Audit & test |
| 14 | `lobster` | Moltbot | ✅ Adapted | Audit & test |
| 15 | `local-places` | Moltbot | ✅ Adapted | Audit & test |
| 16 | `mcporter` | Moltbot | ✅ Ported | Audit & test |
| 17 | `model-usage` | Replace | ✅ Replaced | Audit & test |
| 18 | `nano-banana-pro` | Moltbot | ✅ Ported | Audit & test |
| 19 | `nano-pdf` | Moltbot | ✅ Ported | Audit & test |
| 20 | `notion` | Moltbot | ✅ Ported | Audit & test |
| 21 | `obsidian` | Moltbot | ✅ Ported | Audit & test |
| 22 | `openai-image-gen` | Moltbot | ✅ Ported | Audit & test |
| 23 | `openai-whisper` | Moltbot | ✅ Ported | Audit & test |
| 24 | `openai-whisper-api` | Moltbot | ✅ Ported | Audit & test |
| 25 | `oracle` | Moltbot | ✅ Ported | Audit & test |
| 26 | `sag` | Moltbot | ✅ Ported | Audit & test |
| 27 | `session-logs` | Replace | ✅ Replaced | Audit & test |
| 28 | `sherpa-onnx-tts` | Moltbot | ✅ Adapted | Audit & test |
| 29 | `skill-creator` | Moltbot | ✅ Ported | Audit & test |
| 30 | `skill-registry` | Replace | ✅ Replaced | Audit & test |
| 31 | `slack` | Moltbot | ✅ Ported | Audit & test |
| 32 | `songsee` | Moltbot | ✅ Ported | Audit & test |
| 33 | `summarize` | Moltbot | ✅ Ported | Audit & test |
| 34 | `tmux` | Moltbot | ✅ Ported | Audit & test |
| 35 | `trello` | Moltbot | ✅ Ported | Audit & test |
| 36 | `video-frames` | Moltbot | ✅ Ported | Audit & test |
| 37 | `wacli` | Moltbot | ✅ Adapted | Audit & test |
| 38 | `weather` | Moltbot | ✅ Ported | Audit & test |
| 39 | `echomind-search` | New | ⚠️ Doc stub | Enhance documentation |
| 40 | `echomind-connectors` | New | ⚠️ Doc stub | Enhance documentation |
| 41 | `echomind-documents` | New | ✅ Functional | Audit & test |
| 42 | `echomind-memory` | New | ✅ Functional | Audit & test |
| 43 | `echomind-admin` | New | ❌ Missing | **Create** |
| 44 | `web-scrape` | New | ❌ Missing | **Create** |
| 45-60 | (16 skipped) | N/A | ⏭️ Skipped | No action |

---

## 4. Wave Plan

### Wave 1: Quality Audit & Fixes (Days 1-2)

**Goal**: Ensure all 42 existing skills have valid YAML schema, correct command templates, and pass the registry parser cleanly.

**Tasks:**

1. **Schema validation sweep** — Run the registry parser against all 42 skills, fix any warnings:
   - Placeholder/arg mismatches (e.g., `${arg}` referenced but not in `args:`)
   - Missing `command:` field for doc-only skills
   - Name format violations
   - Duplicate skill names

2. **Remove non-portable skills from registry** — Skills that can never run in a Linux Docker sandbox should either:
   - Have explicit platform guards (checked at registry load time)
   - Be removed from the skills directory entirely
   - Affected: `blucli`, `eightctl`, `imsg` (if still present)

3. **Standardize timeout and output limits** — Ensure every skill has appropriate limits:
   - Read-only/query skills: 15-30s timeout, 64KB output
   - Interactive/API skills: 30-60s timeout, 128KB output
   - Long-running skills (coding-agent, summarize): 120-300s timeout, 256KB output

4. **Verify binary dependencies** — For each skill with `requires.bins`, verify the binary exists in the sandbox Docker image or document what needs installing.

### Wave 2: New EchoMind-Native Skills (Days 3-4)

**Goal**: Create 2 new skills and enhance 2 existing stubs.

#### 2.1 Create `echomind-admin` Skill

System health and administration via EchoMind API.

**File**: `config/mcp-gateway/skills/echomind-admin/SKILL.md`

```yaml
---
name: echomind-admin
description: "Check EchoMind system health, service status, and resource usage"
command: "${command}"
args:
  - name: command
    description: "curl command for EchoMind Admin API"
    required: true
tags: [admin, health, monitoring, system, echomind]
timeout: 15
---
```

**Documentation covers:**
- `GET /healthz` — Service health check
- `GET /api/v1/admin/services` — Service status overview
- `GET /api/v1/admin/stats` — Document count, connector count, storage usage
- `GET /api/v1/admin/users` — User listing (admin only)

#### 2.2 Create `web-scrape` Skill

Extract content from URLs for the agent to analyze.

**File**: `config/mcp-gateway/skills/web-scrape/SKILL.md`

```yaml
---
name: web-scrape
description: "Extract text content from web pages for analysis. Use when the user asks about a URL, article, or web page."
command: "${command}"
args:
  - name: command
    description: "curl command to fetch and extract web content"
    required: true
tags: [web, scrape, url, content, extract]
timeout: 30
max_output_bytes: 131072
---
```

**Documentation covers:**
- `curl -s URL | python3 -c "..."` — HTML to text extraction
- `curl -s URL -H 'User-Agent: ...'` — with proper user agent
- Pipe through `head -n 500` for large pages
- JSON API response handling with `jq`

#### 2.3 Enhance `echomind-search` Documentation

The skill is a documentation pointer to MCP tools. Enhance with:
- Clearer workflow examples
- Multi-collection search strategy
- Score threshold tuning guide
- Example: "Find documents about X across all my collections"

#### 2.4 Enhance `echomind-connectors` Documentation

Enhance with:
- Troubleshooting decision tree (connector errors → remediation)
- Sync scheduling explanation
- "How to add a new connector" walkthrough

### Wave 3: Security Framework (Days 5-6)

**Goal**: Add dangerous command detection and per-skill security controls.

See [Section 8: Security Framework](#8-security-framework) for full details.

### Wave 4: Testing Framework (Days 7-8)

**Goal**: Comprehensive test suite for the skills engine.

See [Section 9: Skill Testing Framework](#9-skill-testing-framework) for full details.

### Wave 5: Sandbox Image & Integration (Days 9-10)

**Goal**: Update sandbox Docker image with all required binaries and run end-to-end validation.

See [Section 7: Sandbox Image Changes](#7-sandbox-image-changes) for full details.

---

## 5. EchoMind-Native Skills Design

### 5.1 `echomind-search` — RAG Search

**Current state**: Documentation-only stub pointing to MCP tools.

**Design decision**: Keep as documentation-only. The search functionality is already exposed as first-class MCP tools (`search_documents`, `list_collections`, `get_collection_info`, `get_document_chunks`). Making this a bash skill that calls `curl` to the API would be redundant and slower than direct MCP tool invocation.

**Enhancement**: Improve the SKILL.md body to serve as a comprehensive guide the agent reads via `skills_get_info("echomind-search")` before using the search MCP tools.

| Aspect | Detail |
|--------|--------|
| **Purpose** | Teach the agent HOW to use EchoMind's RAG pipeline effectively |
| **Type** | Documentation-only (command is echo) |
| **Backend** | MCP search tools (already implemented) |
| **Security** | Collection scoping via user/group/org (Phase 8 adds per-user RBAC) |

### 5.2 `echomind-connectors` — Connector Management

**Current state**: Documentation-only stub pointing to MCP tools.

**Design decision**: Keep as documentation-only. Same rationale as search — connector operations are already first-class MCP tools.

| Aspect | Detail |
|--------|--------|
| **Purpose** | Teach the agent connector management workflows |
| **Type** | Documentation-only |
| **Backend** | MCP connector tools (already implemented) |
| **Security** | Connector ownership check (Phase 8 adds per-user RBAC) |

### 5.3 `echomind-documents` — Document Management

**Current state**: Functional curl-based skill.

| Aspect | Detail |
|--------|--------|
| **Purpose** | List, inspect, and track document processing status |
| **Args schema** | `command: str` (curl command to EchoMind API) |
| **Return schema** | JSON response from API (document list, details, chunks) |
| **Backend** | EchoMind REST API (`/api/v1/documents/`) |
| **Security** | API enforces user scoping; skill runs curl in subprocess |

**Phase 7 action**: Audit, test, and ensure API endpoints are correct.

### 5.4 `echomind-memory` — Agent Long-Term Memory

**Current state**: Functional curl-based skill.

| Aspect | Detail |
|--------|--------|
| **Purpose** | Store and retrieve episodic/semantic memories across sessions |
| **Args schema** | `command: str` (curl command to EchoMind Memory API) |
| **Return schema** | JSON response (memory objects with id, type, content, metadata) |
| **Backend** | EchoMind REST API (`/api/v1/memory/`) |
| **Security** | API enforces user scoping; memories are per-user |

**Phase 7 action**: Audit, test, verify memory API endpoints exist and work.

### 5.5 `echomind-admin` — System Administration (NEW)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Check system health, service status, resource usage |
| **Args schema** | `command: str` (curl command to EchoMind Admin API) |
| **Return schema** | JSON response (health status, service list, stats) |
| **Backend** | EchoMind REST API (`/healthz`, `/api/v1/admin/*`) |
| **Security** | Admin-only endpoints require elevated permissions; read-only health checks are open |

**File path**: `config/mcp-gateway/skills/echomind-admin/SKILL.md`

### 5.6 `web-scrape` — URL Content Extraction (NEW)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Extract text content from web pages for the agent to analyze |
| **Args schema** | `command: str` (curl + text extraction pipeline) |
| **Return schema** | Plain text output (extracted page content) |
| **Backend** | Direct curl + python text extraction (no EchoMind API needed) |
| **Security** | Runs in sandbox with network access; output truncated at 128KB |

**File path**: `config/mcp-gateway/skills/web-scrape/SKILL.md`

---

## 6. Skill YAML Schema

### 6.1 Current Schema (Implemented)

The skill registry (`src/mcp_gateway/skills/registry.py`) parses this format:

```yaml
---
name: skill-name                    # Required: [a-z0-9][a-z0-9-]*, unique
description: "What this skill does" # Required: 1-1024 chars
command: "${arg1} ${arg2}"          # Required: command template with ${} placeholders
args:                               # Optional: argument definitions
  - name: arg1                      # Required per arg
    description: "What arg1 does"   # Optional
    required: true                  # Optional, default false
    default: "value"                # Optional, default null
tags: [tag1, tag2]                  # Optional: categorization tags
timeout: 30                         # Optional: seconds (default 30)
max_output_bytes: 65536             # Optional: output limit (default 64KB)
---

# Skill Title

Markdown documentation body...
```

### 6.2 Schema Validation Rules

Enforced by `SkillRegistry._parse_skill_file()`:

| Rule | Enforcement |
|------|-------------|
| `name` required | ValueError if missing |
| `description` required | ValueError if missing |
| `command` required | ValueError if missing |
| Name format `[a-z0-9][a-z0-9-]*` | Warning logged (not fatal) |
| YAML frontmatter `---` delimiters | ValueError if missing |
| Placeholder/arg mismatch | Warning logged |
| Duplicate skill name | Warning logged, last-wins |

### 6.3 No Schema Changes Needed

The current schema is sufficient. The original design doc proposed `metadata: {"echomind": {...}}` with category, approval, emoji, and requires fields. These are **not implemented** in the current registry parser and are **not needed for Phase 7**. The current flat schema (`name`, `description`, `command`, `args`, `tags`, `timeout`, `max_output_bytes`) covers all requirements.

If category/approval/platform gating is needed in the future, it can be added as new optional frontmatter fields without breaking existing skills.

---

## 7. Sandbox Image Changes

### 7.1 Required Binaries by Skill

| Binary | Skills Using It | Install Method | Size |
|--------|----------------|---------------|------|
| `curl` | weather, web-scrape, openai-*, echomind-* | `apt install curl` | 0.5MB |
| `jq` | trello, web-scrape, API skills | `apt install jq` | 1MB |
| `git` | github | `apt install git` | 30MB |
| `gh` | github | GitHub CLI apt repo | 15MB |
| `python3` | echomind-documents, echomind-memory, web-scrape | Already in base image | — |
| `sed`, `awk` | file-edit | Already in base image | — |
| `ffmpeg` | video-frames | `apt install ffmpeg` | 80MB |
| `tmux` | tmux | `apt install tmux` | 0.5MB |
| `rg` (ripgrep) | coding-agent | `apt install ripgrep` | 5MB |
| `tree` | coding-agent | `apt install tree` | 0.1MB |
| `op` | 1password | 1Password apt repo | 30MB |

### 7.2 Optional Binaries (Defer to User Request)

These are heavy or require API keys and should only be installed when the user explicitly enables the skill:

| Binary | Skill | Size | Notes |
|--------|-------|------|-------|
| `whisper` | openai-whisper | 2GB+ | Local model, use API version instead |
| `sherpa-onnx` | sherpa-onnx-tts | 500MB+ | Local TTS model |
| `nano-pdf` | nano-pdf | 50MB | Python package via pip |

### 7.3 Sandbox Dockerfile Changes

```dockerfile
# Add to src/sandbox/Dockerfile or the sandbox base image

# Core utilities (all skills need these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    git \
    tmux \
    ripgrep \
    tree \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# ffmpeg (for video-frames skill)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
```

### 7.4 Image Size Budget

| Component | Size |
|-----------|------|
| Python 3.12 slim base | ~150MB |
| Core utilities (curl, jq, git, tmux, rg, tree) | ~40MB |
| GitHub CLI | ~15MB |
| ffmpeg | ~80MB |
| **Total estimated** | **~285MB** |

This is well within acceptable limits for an agent sandbox image.

---

## 8. Security Framework

### 8.1 Current Security Posture

The skill executor (`src/mcp_gateway/skills/executor.py`) already implements:

| Control | Implementation |
|---------|---------------|
| Environment isolation | Only PATH, HOME, LANG + explicitly referenced env vars |
| Sensitive var filtering | Blocks KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL, DATABASE_URL |
| Timeout enforcement | `asyncio.wait_for` + process group kill |
| Output truncation | Configurable max_output_bytes per skill |
| Process group killing | `os.killpg(pgid, SIGKILL)` on timeout |
| Argument quoting | `shlex.quote()` for all interpolated values |
| Audit logging | Every tool call logged as structured JSON |

### 8.2 Dangerous Command Detection (Phase 7 Addition)

Add a pattern-based command analyzer to the executor that **logs warnings** for dangerous patterns. Phase 8 will upgrade these to hard blocks.

**File**: `src/mcp_gateway/skills/command_analyzer.py`

```python
"""
Command analyzer for detecting dangerous patterns in skill commands.

Checks commands before execution and classifies risk level.
Logs warnings for risky patterns (Phase 7), blocks them (Phase 8).
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("echomind-mcp-gateway")


class RiskLevel(Enum):
    SAFE = "safe"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class AnalysisResult:
    risk: RiskLevel
    patterns: list[str]
    message: str


# Patterns that should be BLOCKED (Phase 8 enforces, Phase 7 warns)
_BLOCK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'rm\s+(-[rf]+\s+)?/\s'), "Filesystem destruction: rm at root"),
    (re.compile(r'rm\s+-[rf]*\s+/(?:etc|usr|var|boot|sys|proc)'), "System directory deletion"),
    (re.compile(r'mkfs\b'), "Filesystem formatting"),
    (re.compile(r'dd\s+.*of=/dev/'), "Raw device write"),
    (re.compile(r'chmod\s+777\b'), "World-writable permissions"),
    (re.compile(r'curl\s+.*\|\s*(?:ba)?sh'), "Remote code execution: curl | sh"),
    (re.compile(r'wget\s+.*\|\s*(?:ba)?sh'), "Remote code execution: wget | sh"),
    (re.compile(r'>\s*/etc/'), "System config overwrite"),
    (re.compile(r':\(\)\{:\|:&\};:'), "Fork bomb"),
]

# Patterns that should be WARNED (logged but not blocked)
_WARN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'git\s+push\s+--force'), "Force push (history rewrite)"),
    (re.compile(r'git\s+reset\s+--hard'), "Hard reset (data loss risk)"),
    (re.compile(r'\bsudo\b'), "Privilege escalation attempt"),
    (re.compile(r'\bsu\b\s'), "User switching attempt"),
    (re.compile(r'env\b|printenv\b'), "Environment enumeration"),
    (re.compile(r'rm\s+-rf\b'), "Recursive forced deletion"),
    (re.compile(r'>\s*/dev/null\s+2>&1'), "Output suppression (hiding errors)"),
]


def analyze_command(command: str) -> AnalysisResult:
    """
    Analyze a command for dangerous patterns.

    Args:
        command: The bash command to analyze.

    Returns:
        AnalysisResult with risk level, matched patterns, and message.
    """
    matched_patterns: list[str] = []
    risk = RiskLevel.SAFE

    for pattern, description in _BLOCK_PATTERNS:
        if pattern.search(command):
            matched_patterns.append(f"BLOCK: {description}")
            risk = RiskLevel.BLOCK

    if risk != RiskLevel.BLOCK:
        for pattern, description in _WARN_PATTERNS:
            if pattern.search(command):
                matched_patterns.append(f"WARN: {description}")
                if risk == RiskLevel.SAFE:
                    risk = RiskLevel.WARN

    if matched_patterns:
        message = "; ".join(matched_patterns)
        logger.warning(
            f"⚠️ Command risk analysis: {risk.value} — {message}"
        )
    else:
        message = "No dangerous patterns detected"

    return AnalysisResult(
        risk=risk,
        patterns=matched_patterns,
        message=message,
    )
```

### 8.3 Integration with Executor

In `src/mcp_gateway/skills/executor.py`, add command analysis before execution:

```python
from mcp_gateway.skills.command_analyzer import analyze_command, RiskLevel

# In execute() method, before creating subprocess:
analysis = analyze_command(command)
if analysis.risk == RiskLevel.BLOCK:
    # Phase 7: Log and warn, but allow (sandbox provides hard boundary)
    # Phase 8: Return error without executing
    logger.warning(
        f"🚨 Skill '{skill.name}' command flagged as BLOCK-level risk: "
        f"{analysis.message}"
    )
```

### 8.4 Per-Skill Security Considerations

| Skill | Risk Level | Mitigations |
|-------|-----------|-------------|
| `coding-agent` | HIGH | 120s timeout, sandbox network isolation, output limit 256KB |
| `file-edit` | MEDIUM | Runs in /tmp cwd, no access to host filesystem |
| `github` | MEDIUM | Git operations in sandbox, push requires auth |
| `echomind-memory` | LOW | API enforces per-user scoping |
| `weather` | LOW | Read-only curl, 15s timeout |
| `web-scrape` | MEDIUM | Output limit 128KB, timeout 30s, sandboxed |

### 8.5 Filesystem Access Controls (Sandbox-Level)

| Path | Access | Rationale |
|------|--------|-----------|
| `/tmp` | Read-write | Working directory for skill execution |
| `/app` | Read-only | Application code |
| `/app/skills` | Read-only | SKILL.md files |
| `/etc` | Read-only | System config |
| `/usr`, `/bin` | Read-only | System binaries |
| `/proc`, `/sys` | Blocked | Kernel interfaces |

These are enforced by the sandbox container's Docker configuration (read-only root filesystem + tmpfs /tmp), not by the executor.

---

## 9. Skill Testing Framework

### 9.1 Test Directory Structure

```
tests/
  unit/
    mcp_gateway/
      skills/
        __init__.py
        test_registry.py          # SkillRegistry tests
        test_executor.py          # SkillExecutor tests
        test_command_analyzer.py   # Command analyzer tests
        conftest.py               # Shared fixtures
      tools/
        test_skills_tools.py      # MCP tool registration tests
  integration/
    mcp_gateway/
      test_skill_execution.py     # End-to-end skill execution
  fixtures/
    skills/                       # Test skill fixtures
      valid-skill/SKILL.md
      minimal-skill/SKILL.md
      invalid-skill/SKILL.md
      timeout-skill/SKILL.md
```

### 9.2 Registry Tests (`tests/unit/mcp_gateway/skills/test_registry.py`)

| # | Test | Input | Expected |
|---|------|-------|----------|
| 1 | `test_load_valid_skills` | Dir with 3 valid skills | 3 skills loaded |
| 2 | `test_load_empty_dir` | Empty skills directory | 0 skills, no errors |
| 3 | `test_load_missing_dir` | Non-existent path | 0 skills, warning logged |
| 4 | `test_load_mixed_valid_invalid` | 2 valid + 1 malformed | 2 loaded, 1 error logged |
| 5 | `test_parse_required_fields` | name + description + command | Valid SkillDefinition |
| 6 | `test_parse_missing_name` | No name field | ValueError |
| 7 | `test_parse_missing_description` | No description field | ValueError |
| 8 | `test_parse_missing_command` | No command field | ValueError |
| 9 | `test_parse_missing_frontmatter` | No `---` delimiters | ValueError |
| 10 | `test_parse_args` | 2 args with defaults | SkillDefinition with args |
| 11 | `test_parse_tags` | tags: [a, b, c] | SkillDefinition with tags |
| 12 | `test_parse_custom_timeout` | timeout: 120 | SkillDefinition.timeout == 120 |
| 13 | `test_parse_documentation_body` | Markdown after frontmatter | Body in documentation field |
| 14 | `test_get_skill_found` | Known skill name | Returns SkillDefinition |
| 15 | `test_get_skill_not_found` | Unknown name | Returns None |
| 16 | `test_list_skills` | 3 loaded skills | List of 3 summary dicts |
| 17 | `test_skill_count` | 3 loaded skills | skill_count == 3 |
| 18 | `test_placeholder_validation` | Mismatched placeholders/args | Warning logged |
| 19 | `test_duplicate_name_warning` | Two dirs with same skill name | Warning logged, last-wins |
| 20 | `test_invalid_name_format` | name: "My Skill" | Warning logged |

### 9.3 Executor Tests (`tests/unit/mcp_gateway/skills/test_executor.py`)

| # | Test | Command | Expected |
|---|------|---------|----------|
| 1 | `test_execute_success` | `echo hello` | success=True, stdout="hello\n" |
| 2 | `test_execute_failure` | `exit 1` | success=False, exit_code=1 |
| 3 | `test_execute_timeout` | `sleep 60` (timeout=1s) | timed_out=True |
| 4 | `test_execute_output_truncation` | `seq 1 1000000` (limit=1024B) | Output truncated |
| 5 | `test_execute_stderr` | `echo err >&2` | stderr="err\n" |
| 6 | `test_execute_empty_command` | `""` | Graceful error |
| 7 | `test_safe_env_base_keys` | Any command | PATH, HOME, LANG in env |
| 8 | `test_safe_env_blocks_secrets` | Command with `$SECRET_KEY` | SECRET_KEY not in env |
| 9 | `test_safe_env_passes_referenced` | Command with `$GOOGLE_CX` | GOOGLE_CX passed if set |
| 10 | `test_arg_interpolation` | `echo ${name}` with args={"name": "world"} | stdout="world\n" |
| 11 | `test_arg_shell_quoting` | `echo ${name}` with args={"name": "; rm -rf /"} | Quoted safely |
| 12 | `test_missing_required_arg` | Required arg not provided | success=False, error message |
| 13 | `test_default_arg_applied` | Optional arg with default | Default used |
| 14 | `test_process_group_killed_on_timeout` | `sleep 60` | Process reaped |
| 15 | `test_non_utf8_output` | Binary output | Decoded with replace |

### 9.4 Command Analyzer Tests (`tests/unit/mcp_gateway/skills/test_command_analyzer.py`)

| # | Test | Command | Expected |
|---|------|---------|----------|
| 1 | `test_safe_command` | `echo hello` | RiskLevel.SAFE |
| 2 | `test_block_rm_root` | `rm -rf /` | RiskLevel.BLOCK |
| 3 | `test_block_rm_system_dirs` | `rm -rf /etc` | RiskLevel.BLOCK |
| 4 | `test_block_curl_pipe_sh` | `curl http://x \| sh` | RiskLevel.BLOCK |
| 5 | `test_block_chmod_777` | `chmod 777 /tmp` | RiskLevel.BLOCK |
| 6 | `test_block_fork_bomb` | `:(){ :\|:& };:` | RiskLevel.BLOCK |
| 7 | `test_warn_force_push` | `git push --force` | RiskLevel.WARN |
| 8 | `test_warn_hard_reset` | `git reset --hard` | RiskLevel.WARN |
| 9 | `test_warn_sudo` | `sudo apt install` | RiskLevel.WARN |
| 10 | `test_warn_rm_rf` | `rm -rf ./build` | RiskLevel.WARN |
| 11 | `test_safe_git_status` | `git status` | RiskLevel.SAFE |
| 12 | `test_safe_curl` | `curl -s https://api.example.com` | RiskLevel.SAFE |
| 13 | `test_multiple_patterns` | `sudo rm -rf /` | RiskLevel.BLOCK (worst wins) |

### 9.5 MCP Tools Tests (`tests/unit/mcp_gateway/tools/test_skills_tools.py`)

| # | Test | Flow | Expected |
|---|------|------|----------|
| 1 | `test_skills_list_returns_all` | Registry with 3 skills | List of 3 summaries |
| 2 | `test_skills_get_info_found` | Known skill | Full detail with docs |
| 3 | `test_skills_get_info_not_found` | Unknown name | SkillNotFoundError |
| 4 | `test_skills_execute_success` | `echo test` | success=True |
| 5 | `test_skills_execute_not_found` | Unknown skill | SkillNotFoundError |
| 6 | `test_skills_execute_timeout` | Slow command | SkillTimeoutError |
| 7 | `test_skills_execute_failure` | `exit 1` | SkillExecutionError |

### 9.6 Integration Tests (`tests/integration/mcp_gateway/test_skill_execution.py`)

| # | Test | Skill | Expected |
|---|------|-------|----------|
| 1 | `test_weather_skill` | weather | curl returns weather data |
| 2 | `test_file_edit_skill` | file-edit | sed modifies test file |
| 3 | `test_github_skill_status` | github | `git status` returns output |
| 4 | `test_echomind_docs_skill` | echomind-documents | curl returns API response |
| 5 | `test_web_scrape_skill` | web-scrape | curl extracts page text |
| 6 | `test_list_info_execute_flow` | Any skill | Full 3-step MCP flow |

### 9.7 Running Tests

```bash
# Unit tests only (fast, no external deps)
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest \
  tests/unit/mcp_gateway/skills/ -v

# Integration tests (require MCP gateway running)
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest \
  tests/integration/mcp_gateway/test_skill_execution.py -v

# All MCP gateway tests with coverage
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest \
  tests/unit/mcp_gateway/ tests/integration/mcp_gateway/ \
  --cov=src/mcp_gateway --cov-report=term-missing -v
```

---

## 10. Per-Skill Implementation Detail

### 10.1 New Skills

#### `echomind-admin` (NEW)

| Aspect | Detail |
|--------|--------|
| File | `config/mcp-gateway/skills/echomind-admin/SKILL.md` |
| Dependencies | `curl`, `jq`, `python3` (all in sandbox image) |
| Backend | EchoMind REST API |
| Test plan | Unit: YAML parsing. Integration: curl to API healthz returns 200 |

#### `web-scrape` (NEW)

| Aspect | Detail |
|--------|--------|
| File | `config/mcp-gateway/skills/web-scrape/SKILL.md` |
| Dependencies | `curl`, `python3` (all in sandbox image) |
| Backend | Direct HTTP fetch (no EchoMind API) |
| Test plan | Unit: YAML parsing. Integration: curl to example.com returns HTML text |

### 10.2 Enhanced Skills

#### `echomind-search` (ENHANCE)

| Aspect | Detail |
|--------|--------|
| File | `config/mcp-gateway/skills/echomind-search/SKILL.md` |
| Change | Expand documentation body with workflow examples |
| Test plan | Verify YAML parsing; manual test of agent workflow |

#### `echomind-connectors` (ENHANCE)

| Aspect | Detail |
|--------|--------|
| File | `config/mcp-gateway/skills/echomind-connectors/SKILL.md` |
| Change | Add troubleshooting guide and connector lifecycle docs |
| Test plan | Verify YAML parsing; manual test of agent workflow |

### 10.3 Security Additions

#### `command_analyzer.py` (NEW)

| Aspect | Detail |
|--------|--------|
| File | `src/mcp_gateway/skills/command_analyzer.py` |
| Dependencies | `re` (stdlib only) |
| Test plan | 13 unit tests covering all pattern categories |

#### Executor integration (MODIFY)

| Aspect | Detail |
|--------|--------|
| File | `src/mcp_gateway/skills/executor.py` |
| Change | Import and call `analyze_command()` before subprocess creation |
| Test plan | Existing executor tests + new analyzer tests |

---

## 11. Implementation Order

### Build Sequence with Dependencies

```
Day 1-2: Wave 1 — Quality Audit
  ├─ Audit all 42 SKILL.md files for schema compliance
  ├─ Remove/guard non-portable skills
  ├─ Standardize timeouts and output limits
  └─ Document binary dependencies

Day 3-4: Wave 2 — New Skills
  ├─ Create echomind-admin/SKILL.md
  ├─ Create web-scrape/SKILL.md
  ├─ Enhance echomind-search/SKILL.md documentation
  └─ Enhance echomind-connectors/SKILL.md documentation

Day 5-6: Wave 3 — Security
  ├─ Create command_analyzer.py (no dependencies)
  ├─ Write command_analyzer tests
  ├─ Integrate analyzer into executor.py
  └─ Verify existing executor tests still pass

Day 7-8: Wave 4 — Testing
  ├─ Create test fixtures (valid/invalid SKILL.md files)
  ├─ Write registry unit tests (20 tests)
  ├─ Write executor unit tests (15 tests)
  ├─ Write MCP tools unit tests (7 tests)
  └─ Write integration tests (6 tests)

Day 9-10: Wave 5 — Sandbox & Integration
  ├─ Update sandbox Dockerfile with required binaries
  ├─ Build and test sandbox image locally
  ├─ Run full integration test suite
  └─ Verify all 42+ skills load cleanly in Docker
```

### Dependency Graph

```
Wave 1 (Audit) ─────────────── no dependencies
Wave 2 (New Skills) ─────────── no dependencies
Wave 3 (Security) ──────────── depends on Wave 1 (clean executor)
Wave 4 (Testing) ───────────── depends on Waves 1-3 (all code stable)
Wave 5 (Sandbox) ───────────── depends on Wave 1 (binary list) + Wave 4 (tests pass)
```

Waves 1 and 2 can run in parallel. Wave 3 depends on Wave 1. Wave 4 depends on all code changes being complete. Wave 5 is the final integration step.

---

## 12. Evaluation Scorecard

| # | Criterion | Score (1-10) | Justification |
|---|-----------|-------------|---------------|
| 1 | **Completeness** | 9/10 | 42 skills ported + 2 new + 2 enhanced + 16 deliberately skipped with documentation. Full coverage of EchoMind's needs. |
| 2 | **Security posture** | 7/10 | Environment isolation, output limits, timeout enforcement, and command analysis all present. Full blocking deferred to Phase 8 (requires auth context). Sandbox provides hard boundary. |
| 3 | **Test coverage** | 8/10 | 61 planned tests across 4 test files. Covers parser, executor, analyzer, tools, and integration. Edge cases for timeouts, truncation, and shell injection included. |
| 4 | **Developer experience** | 9/10 | Adding a skill = create directory + write SKILL.md. No Python code, no compilation. Hot reload via registry rescan. |
| 5 | **EchoMind integration** | 8/10 | Native skills cover search, documents, connectors, and memory. All integrated via existing MCP tools or REST API. Admin skill adds operational visibility. |
| 6 | **Sandbox readiness** | 8/10 | Binary dependency matrix complete. Dockerfile changes specified. Image size budget acceptable (~285MB). Only optional heavy binaries (whisper, sherpa-onnx) deferred. |
| 7 | **Migration risk** | 9/10 | Most skills already ported and loaded. Phase 7 is primarily quality assurance, testing, and polish — not a risky migration. Rollback = revert SKILL.md file changes. |

**Overall: 8.3/10** — Strong foundation with comprehensive coverage. Security hardening (command blocking) and auth-aware per-user scoping are well-defined for Phase 8.

---

## 13. References

| Document | Relevance |
|----------|-----------|
| `agent_docs/agent_execution-plan.md` | Master execution plan (Phases 1-8) |
| `agent_docs/agent_mcp-gateway.md` | MCP gateway architecture, tool schemas |
| `agent_docs/skipped-skills.md` | Why 16 skills are not ported |
| `src/mcp_gateway/skills/registry.py` | Current skill parser implementation |
| `src/mcp_gateway/skills/executor.py` | Current skill executor implementation |
| `src/mcp_gateway/tools/skills.py` | MCP tool registration for skills |
| `config/mcp-gateway/skills/` | All 42 skill SKILL.md files |
| [FastMCP 3.x Docs](https://gofastmcp.com) | MCP framework reference |
| [MCP Spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) | Protocol specification |
| [NVIDIA Sandbox Security](https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/) | Sandbox security patterns |
| [OWASP AI Agent Security Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | Agent security risks |

---

## Appendix A: Original Analysis (Preserved)

> The original analysis document that preceded this execution plan examined all 53 Moltbot skills, mapped 30 EchoMind native tools to bash equivalents, and established the SKILL.md format. Key findings:
>
> - 73% of EchoMind's 30 native Python tools were thin shell wrappers
> - 27 of 53 Moltbot skills were directly portable, 7 needed adaptation, 19 were platform-specific
> - The skill-as-MCP-tool pattern adds ~10-50ms latency (negligible) with mandatory sandbox security
>
> The analysis was validated during Phases 1-4 implementation. All portable skills were successfully ported. The SKILL.md format with YAML frontmatter + markdown body is working as designed.
