# EchoMind MCP Gateway Server Design

> Single MCP server that serves as the gateway for agent skills, connectors, and API keys.
> Runs OUTSIDE the sandbox as a shared service. Agents in ephemeral containers connect via Streamable HTTP.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Why FastMCP](#why-fastmcp)
3. [Auth & Security Model](#auth--security-model)
4. [MCP Tool Catalog](#mcp-tool-catalog)
5. [Skills via MCP](#skills-via-mcp)
6. [SKILL.md Format Specification](#skillmd-format-specification)
7. [Skill Flow Sequence Diagram](#skill-flow-sequence-diagram)
8. [Connectors via MCP](#connectors-via-mcp)
9. [API Key Management](#api-key-management)
10. [Detailed Implementation Plan](#detailed-implementation-plan)
11. [Docker Compose Service Definition](#docker-compose-service-definition)
12. [Deployment & Operations](#deployment--operations)
13. [Integration with Existing Agent System](#integration-with-existing-agent-system)
14. [Dependencies](#dependencies)
15. [Test Plan](#test-plan)
16. [Evaluation Scorecard](#evaluation-scorecard)
17. [Citations and Sources](#citations-and-sources)

---

## Architecture Overview

```
+------------------------------------------------------------------+
|  Ephemeral Sandbox Container (per agent invocation)              |
|                                                                    |
|  +--------------------+    Streamable HTTP    +------------------+ |
|  | Agent (SK Runtime)  | ===================> | MCP Gateway      | |
|  | - No API keys       |    (port 8100)       | (echomind-mcp)   | |
|  | - No DB access      |                      |                  | |
|  | - No network egress |                      | Runs OUTSIDE     | |
|  |   (except MCP)      |                      | sandbox          | |
|  +--------------------+                      +--------+---------+ |
+------------------------------------------------------------------+
                                                         |
                    +------------------------------------+------------------------------------+
                    |                    |                    |                    |
           +-------v-------+   +--------v--------+   +------v------+   +---------v---------+
           | PostgreSQL     |   | Qdrant           |   | MinIO       |   | External APIs     |
           | (sessions,     |   | (vector search)  |   | (documents) |   | (Google, MSFT,    |
           | connectors)    |   |                  |   |             |   |  OpenAI, etc.)    |
           +---------------+   +------------------+   +-------------+   +-------------------+
```

### Key Design Principles

1. **Agent sees only MCP tools** -- no raw API keys, no direct DB connections, no network access
2. **Audit logging on every call** -- tool name, parameters, result status, duration logged as structured JSON
3. **Single service, multiple tool namespaces** -- skills, connectors, search, and API proxying all in one FastMCP server
4. **No auth in initial phase** -- All callers trusted. Network isolation (internal Docker network) provides security. Auth (JWT, RBAC, rate limiting) deferred to Phase 8 (security hardening).

---

## Why FastMCP

### Decision: FastMCP 3.x (not from scratch)

| Criteria | FastMCP | From Scratch |
|----------|---------|--------------|
| MCP protocol compliance | Built-in, tested | Must implement spec |
| Transport support | stdio, HTTP, SSE, memory | Must build each |
| Schema generation | Automatic from type hints | Manual JSON Schema |
| Middleware stack | Built-in (logging, rate limit, error handling) | Must build |
| Server composition | `mount()`, `ProxyProvider` | Manual routing |
| Observability | Native instrumentation | Must integrate |
| Community | 70% of MCP servers use it | N/A |
| Maintenance | Active (3.0.0rc2 released 2026-02-14) | Team burden |

**FastMCP provides the entire infrastructure layer**. Building from scratch would duplicate months of protocol work with no strategic advantage. The framework's middleware system directly maps to our audit logging and error handling requirements.

### FastMCP Features We Use

- **`@mcp.tool` decorator** -- Expose Python functions as MCP tools with auto-generated schemas
- **`Context` injection** -- Access session state, logging, progress reporting inside tools (`from fastmcp.server.context import Context`)
- **Middleware stack** -- Audit logging, error handling as composable `Middleware` subclasses with `on_call_tool` hooks
- **Streamable HTTP transport** -- Production deployment over network via `mcp.run(transport="http")`
- **Custom routes** -- `@mcp.custom_route("/healthz")` for health check endpoints alongside MCP protocol
- **Server composition** -- Mount skill/connector/search namespaces into one server

### FastMCP Version Strategy

FastMCP 3.0 is currently in release candidate (3.0.0rc2 as of 2026-02-14). The stable release is 2.14.5. Our strategy:

- **Start with `fastmcp>=2.14,<3`** for production stability
- **Track 3.0 RC** -- middleware API, Context, and tool decorators are stable across 2.x and 3.x
- **Upgrade to 3.0 stable** when released (expected early March 2026)
- The APIs we use (`@mcp.tool`, `Context`, `Middleware`, `mcp.run(transport="http")`) are identical in 2.14 and 3.0

---

## Auth & Security Model

### Initial Phase: No Auth (Phase 1)

**No JWT, no RBAC, no PermissionChecker, no rate limiting in the initial implementation.** All callers are trusted.

Auth is deferred to Phase 8 (security hardening) per the execution plan. The rationale:

1. **Internal Docker network provides sufficient isolation** -- the MCP gateway is only reachable from the `backend` and `sandbox` Docker networks, not from the internet
2. **Auth adds complexity that slows iteration** on the core skill/sandbox flow
3. **All auth infrastructure already exists** (JWT, RBAC, PermissionChecker) -- wiring it in is mechanical work once the core is proven

### What We Do Instead: Audit Logging

Every MCP tool invocation is logged as structured JSON. This provides full observability without the complexity of auth:

```json
{
  "timestamp": "2026-02-16T14:30:00.123Z",
  "event": "mcp_tool_call",
  "tool": "search_documents",
  "parameters": {"query": "quarterly report", "limit": 10},
  "result_status": "success",
  "duration_ms": 234,
  "error": null
}
```

The audit log captures:
- **tool**: Which MCP tool was called
- **parameters**: Input arguments (sensitive values redacted)
- **result_status**: `"success"` or `"error"`
- **duration_ms**: Execution time
- **error**: Error message if failed, `null` otherwise
- **timestamp**: ISO 8601 UTC timestamp

### Defense Layers (Initial Phase)

```
Layer 1: Network Isolation
  - MCP gateway runs on internal Docker network only
  - Not exposed to the internet
  - Only reachable from backend and sandbox networks

Layer 2: Audit Logging (every call)
  - Every tool invocation logged with structured JSON
  - Shipped to stdout for Docker log aggregation

Layer 3: Skill Sandboxing
  - Skills run in subprocess with resource limits
  - Timeout enforcement (30s default, configurable per skill)
  - Output size limits (64KB default)
  - No inherited secrets from gateway process
```

### Future: Auth Added in Phase 8

Phase 8 will add:
- JWT bearer token validation on every MCP request (RS256, 15-min TTL)
- `SessionContext` extraction: session_id, user_id, org_id, groups, permissions
- RBAC enforcement via existing `PermissionChecker` from `src/api/logic/permissions.py`
- Per-user per-tool rate limiting (sliding window)
- Collection scoping for Qdrant searches (user/team/org)

---

## MCP Tool Catalog

The gateway exposes tools in two namespaces for Phase 1:

### Namespace Overview (Phase 1)

| Namespace | Tools | Description |
|-----------|-------|-------------|
| `skills` | `skills_list`, `skills_execute`, `skills_get_info` | SKILL.md-based bash skills |
| `search` | `search_documents`, `search_collections`, `get_document`, `get_document_chunks` | RAG retrieval from Qdrant |

### Future Namespaces (Phase 2+)

| Namespace | Tools | Description |
|-----------|-------|-------------|
| `connectors` | `connectors_list`, `connector_status`, `connector_sync` | Data source management |
| `api` | `web_search`, `send_email`, `calendar_create_event` | Proxied external API calls |

### Full Tool Schema Definitions

```python
from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

mcp = FastMCP("EchoMind Gateway")


# ─── Skills Namespace ──────────────────────────────────────────────

class SkillInfo(BaseModel):
    """Metadata about an available skill."""
    name: str = Field(..., description="Skill identifier")
    description: str = Field(..., description="What the skill does")
    parameters: list[dict] = Field(default_factory=list, description="Expected parameters")
    tags: list[str] = Field(default_factory=list, description="Skill tags for categorization")


class SkillDetailInfo(BaseModel):
    """Full skill information including instructions body."""
    name: str = Field(..., description="Skill identifier")
    description: str = Field(..., description="What the skill does")
    parameters: list[dict] = Field(default_factory=list, description="Expected parameters")
    tags: list[str] = Field(default_factory=list, description="Skill tags for categorization")
    instructions: str = Field(..., description="Full SKILL.md body with usage instructions")


class SkillExecuteResult(BaseModel):
    """Result of skill execution."""
    success: bool
    output: str
    exit_code: int
    duration_ms: int


@mcp.tool
async def skills_list(ctx: Context) -> list[SkillInfo]:
    """List all available skills with their names, descriptions, and parameters."""
    ...


@mcp.tool
async def skills_get_info(ctx: Context, skill_name: str) -> SkillDetailInfo:
    """
    Get detailed information about a specific skill including full instructions.
    Call this before skills_execute to understand how to use the skill.
    """
    ...


@mcp.tool
async def skills_execute(
    ctx: Context,
    skill_name: str,
    command: str,
) -> SkillExecuteResult:
    """
    Execute a bash command in the context of a skill.
    The command runs in a subprocess with timeout and output limits.
    Use skills_get_info first to learn the skill's bash patterns.
    """
    ...


# ─── Search Namespace ──────────────────────────────────────────────

class SearchResult(BaseModel):
    """A document chunk from vector search."""
    document_id: int
    chunk_id: str
    title: str
    content: str
    score: float
    source_url: str | None = None
    connector_type: str | None = None


@mcp.tool
async def search_documents(
    ctx: Context,
    query: str,
    limit: int = 10,
    score_threshold: float = 0.5,
) -> list[SearchResult]:
    """
    Search documents using semantic similarity.
    Returns ranked document chunks matching the query.
    """
    ...


@mcp.tool
async def search_collections(ctx: Context) -> list[dict]:
    """List available Qdrant collections with stats (vector count, status)."""
    ...


@mcp.tool
async def get_document(ctx: Context, document_id: int) -> dict:
    """Get document metadata by ID (title, source, connector type, created date)."""
    ...


@mcp.tool
async def get_document_chunks(
    ctx: Context,
    document_id: int,
    limit: int = 20,
) -> list[dict]:
    """Get all chunks for a document. For reading full document content after search."""
    ...
```

---

## Skills via MCP

### Skill Discovery

Skills are SKILL.md files in a configured directory. Each file follows a structured format that the gateway parses into MCP tool metadata:

```
skills/
  github/
    SKILL.md          # Metadata + instructions
  weather/
    SKILL.md
  file-edit/
    SKILL.md
  summarize/
    SKILL.md
  coding-agent/
    SKILL.md
```

Note: Unlike the original design where each skill had a separate executable script, the MCP gateway executes bash commands directly via `skills_execute(skill_name, command)`. The SKILL.md body teaches the agent which bash patterns to use. No separate `.sh` or `.py` executables are needed.

### Skill Execution Engine

```python
import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default execution limits
DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_MAX_OUTPUT_BYTES: int = 65_536  # 64KB


@dataclass
class SkillDefinition:
    """Parsed SKILL.md definition."""

    name: str
    description: str
    parameters: list[dict[str, Any]]
    tags: list[str]
    instructions: str  # Full SKILL.md body (markdown)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES


class SkillRegistry:
    """
    Discovers and manages skills from filesystem.

    Scans a directory for SKILL.md files, parses them,
    and caches SkillDefinition objects for fast lookup.
    """

    def __init__(self, skills_dir: str) -> None:
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}

    async def discover(self) -> None:
        """Scan skills directory and parse all SKILL.md files."""
        if not self._skills_dir.exists():
            logger.warning(f"⚠️ Skills directory not found: {self._skills_dir}")
            return

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                skill = self._parse_skill_md(skill_dir.name, skill_md)
                self._skills[skill.name] = skill
                logger.info(f"🔧 Discovered skill: {skill.name}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse skill {skill_dir.name}: {e}")

        logger.info(f"🔧 Discovered {len(self._skills)} skills total")

    def list_skills(self) -> list[SkillDefinition]:
        """
        List all discovered skills.

        Returns:
            All registered SkillDefinition objects.
        """
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillDefinition | None:
        """
        Get a skill by name.

        Args:
            name: Skill identifier.

        Returns:
            SkillDefinition if found, None otherwise.
        """
        return self._skills.get(name)

    @property
    def skill_count(self) -> int:
        """Return number of discovered skills."""
        return len(self._skills)

    def _parse_skill_md(self, name: str, path: Path) -> SkillDefinition:
        """
        Parse a SKILL.md file into a SkillDefinition.

        Extracts YAML frontmatter for metadata and uses the
        markdown body as instructions.

        Args:
            name: Skill directory name (used as skill identifier).
            path: Path to SKILL.md file.

        Returns:
            Populated SkillDefinition.

        Raises:
            ValueError: If SKILL.md is malformed or missing required fields.
        """
        content = path.read_text()
        # Parse YAML frontmatter and markdown body
        # See SKILL.md Format Specification section
        ...
```

---

## SKILL.md Format Specification

Each skill is defined by a `SKILL.md` file inside a directory named after the skill. The file has two parts: **YAML frontmatter** (metadata) and **markdown body** (instructions).

### Format

```
---
name: <skill-identifier>
description: <one-line description>
parameters:
  - name: <param-name>
    description: <what it does>
    required: <true|false>
    default: <default-value>
tags: [<tag1>, <tag2>, ...]
timeout_seconds: <int, default 30>
max_output_bytes: <int, default 65536>
---

<markdown body: instructions, examples, bash patterns>
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | directory name | Skill identifier (lowercase, hyphens) |
| `description` | string | Yes | -- | One-line description shown in `skills_list()` |
| `parameters` | list | No | `[]` | Expected parameters with name, description, required, default |
| `tags` | list[str] | No | `[]` | Categorization tags |
| `timeout_seconds` | int | No | `30` | Max execution time for subprocess |
| `max_output_bytes` | int | No | `65536` | Max stdout capture size (64KB) |

### Example: GitHub Skill

```markdown
---
name: github
description: Manage GitHub repositories, PRs, issues, and actions using the gh CLI
parameters:
  - name: repo
    description: Target repository in owner/name format
    required: false
  - name: command
    description: The gh CLI subcommand to run
    required: true
tags: [github, git, pr, issues, ci]
timeout_seconds: 60
max_output_bytes: 131072
---

# GitHub Skill

Interact with GitHub using the `gh` CLI. You have full access to the GitHub CLI.

## Common Patterns

### List PRs
```bash
gh pr list --repo owner/name --limit 10
```

### Create a PR
```bash
gh pr create --repo owner/name --title "Fix bug" --body "Description"
```

### View PR details
```bash
gh pr view 123 --repo owner/name
```

### List issues
```bash
gh issue list --repo owner/name --state open
```

### Run a workflow
```bash
gh workflow run deploy.yml --repo owner/name
```

## Notes
- Always specify `--repo owner/name` unless working in a git directory
- Use `--json` flag for structured output when parsing results
```

### Example: Weather Skill (Simple)

```markdown
---
name: weather
description: Get weather information for any location using wttr.in
parameters:
  - name: location
    description: City name or coordinates
    required: true
tags: [weather, utility]
timeout_seconds: 15
---

# Weather Skill

Get weather forecasts using wttr.in.

## Usage
```bash
curl -s "wttr.in/Zurich?format=3"
```

## Detailed forecast
```bash
curl -s "wttr.in/Zurich"
```

## JSON output
```bash
curl -s "wttr.in/Zurich?format=j1"
```
```

### Parsing Logic

The SKILL.md parser:
1. Splits the file on `---` delimiters to extract YAML frontmatter
2. Parses the frontmatter with `yaml.safe_load()`
3. The remaining content after the second `---` is the markdown body (instructions)
4. If `name` is missing from frontmatter, falls back to the directory name
5. If `description` is missing, raises `ValueError`

---

## Skill Flow Sequence Diagram

```
Agent                              MCP Gateway
  |                                     |
  |-- skills_list() ------------------>|  Parse all SkillDefinition objects
  |<-- [{name, description, params}] --|  Return compact list (no instructions body)
  |                                     |
  |  (Agent reads the list and         |
  |   decides: "I need the 'github'   |
  |   skill to list PRs")             |
  |                                     |
  |-- skills_get_info("github") ------>|  Look up SkillDefinition by name
  |<-- {name, description, params,   --|  Return FULL SKILL.md body as instructions
  |     instructions: "# GitHub..."}   |  (agent now knows the bash patterns)
  |                                     |
  |-- skills_execute("github",  ------>|  Run command in subprocess:
  |     "gh pr list --repo X")         |    - cwd = skills/github/
  |                                     |    - timeout = skill.timeout_seconds
  |                                     |    - stdout capped at max_output_bytes
  |<-- {success: true,              ---|  Return execution result
  |     output: "PR #1 ...",           |
  |     exit_code: 0,                  |
  |     duration_ms: 1234}             |
  |                                     |
  |  (Agent may call skills_execute    |
  |   multiple times for multi-step    |
  |   tasks, using the same skill)     |
  |                                     |
  |-- skills_execute("github",  ------>|  Each call is independent
  |     "gh pr view 42 --repo X")      |
  |<-- {success: true, ...}         ---|
```

### Key Flow Properties

1. **Progressive disclosure**: `skills_list()` returns compact metadata only. Full instructions are loaded on demand via `skills_get_info()`.
2. **Agent decides**: The LLM agent reads the skill list and chooses which skill to use based on the user's request. The gateway does not make this decision.
3. **Command construction**: After reading `skills_get_info()`, the agent constructs bash commands following the skill's documented patterns.
4. **Stateless execution**: Each `skills_execute()` call runs a fresh subprocess. No state persists between calls.

---

## Connectors via MCP

> **Note**: Connectors are Phase 2 scope. Included here for reference.

### User-Scoped Access Pattern

The MCP gateway will reuse the existing `PermissionChecker` from `src/api/logic/permissions.py` once auth is added in Phase 8. In the initial phase, connector tools return all connectors without RBAC filtering.

### Collection Scoping Rules

The gateway enforces the same collection scoping as the existing API:

| Scope | Qdrant Collection Name | Who Can Search |
|-------|----------------------|----------------|
| User  | `user_{user_id}`     | Owner only |
| Team  | `team_{team_id}`     | Team members |
| Org   | `org_default`        | All allowed users |

This logic is already implemented in `PermissionChecker.get_search_collections()` at `src/api/logic/permissions.py`. The MCP gateway will reuse it directly once auth is wired in (Phase 8).

In Phase 1, the search backend searches all available collections without user scoping. This is acceptable because:
- The MCP gateway is only reachable from internal Docker networks
- User scoping is enforced by the API service that creates the sandbox session

---

## API Key Management

### Principle: Agent Never Sees Raw Keys

API keys are stored in the MCP gateway's environment (loaded from secrets/vault). When an agent calls an MCP tool that needs an external API, the gateway:

1. Looks up the required API key by service name
2. Makes the authenticated HTTP call on the agent's behalf
3. Returns only the response data to the agent

```
Agent calls:       web_search(query="latest news")
MCP Gateway does:  GET https://api.google.com/search?q=latest+news
                   Authorization: Bearer <GOOGLE_API_KEY>   <-- agent never sees this
Returns to agent:  [{"title": "...", "url": "...", "snippet": "..."}]
```

> **Note**: API proxy tools are Phase 2 scope. In Phase 1, only skills and search are available.

### Registered API Keys (Phase 2+)

| Service | Env Var | Rate Limit |
|---------|---------|------------|
| `google_search` | `GOOGLE_SEARCH_API_KEY` | 100/min |
| `openai` | `OPENAI_API_KEY` | 30/min |
| `anthropic` | `ANTHROPIC_API_KEY` | 30/min |

For OAuth-based services (Google, Microsoft), the gateway will retrieve the user's refresh token from the database and exchange it for a short-lived access token. The agent never sees the refresh token or access token.

---

## Detailed Implementation Plan

### Complete File Tree

```
src/mcp_gateway/
  __init__.py                    # Package marker
  main.py                        # FastMCP server setup, tool registration, startup
  config.py                      # Pydantic Settings with MCP_GATEWAY_ env prefix
  middleware/
    __init__.py                  # Package marker
    audit_logger.py              # Structured JSON audit logging middleware
    error_handler.py             # Domain exception -> MCP ToolError mapping
  tools/
    __init__.py                  # Package marker, registers all tools on mcp instance
    search.py                    # search_documents, search_collections, get_document, get_document_chunks
    skills.py                    # skills_list, skills_get_info, skills_execute
  skills/
    __init__.py                  # Package marker
    registry.py                  # SkillRegistry: SKILL.md parser, discovery, caching
    executor.py                  # SkillExecutor: subprocess execution with timeout, output limits
    exceptions.py                # SkillNotFoundError, SkillTimeoutError
  backends/
    __init__.py                  # Package marker
    search_backend.py            # SearchBackend: Qdrant + Embedder gRPC integration
  Dockerfile                     # Multi-stage build
  requirements.txt               # Pinned dependencies
```

### File-by-File Specification

---

#### `src/mcp_gateway/main.py` -- FastMCP Server Entrypoint

**Purpose**: Create the FastMCP server, register all tools, add middleware, configure health check, and run with Streamable HTTP transport.

```python
"""
MCP Gateway Server -- Entrypoint.

Creates and configures the FastMCP server with all tool namespaces,
middleware, and health checks. Runs on Streamable HTTP transport.
"""

import asyncio
import logging

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from mcp_gateway.config import get_settings, MCPGatewaySettings
from mcp_gateway.middleware.audit_logger import AuditLoggingMiddleware
from mcp_gateway.middleware.error_handler import ErrorHandlingMiddleware
from mcp_gateway.tools import register_all_tools
from mcp_gateway.skills.registry import SkillRegistry
from mcp_gateway.backends.search_backend import SearchBackend

logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    """
    Create and configure the MCP gateway server.

    Returns:
        Configured FastMCP instance with all tools and middleware.
    """
    settings = get_settings()

    mcp = FastMCP("EchoMind Gateway")

    # Add middleware (order matters: error handling first, audit last)
    mcp.add_middleware(ErrorHandlingMiddleware())
    mcp.add_middleware(AuditLoggingMiddleware())

    # Initialize backends
    search_backend = SearchBackend(
        qdrant_host=settings.qdrant_host,
        qdrant_port=settings.qdrant_port,
        embedder_host=settings.embedder_host,
        embedder_port=settings.embedder_port,
    )

    # Initialize skill registry
    skill_registry = SkillRegistry(skills_dir=settings.skills_dir)

    # Register all tools (passes backends to tool functions via closure)
    register_all_tools(
        mcp=mcp,
        search_backend=search_backend,
        skill_registry=skill_registry,
    )

    # Health check endpoint
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> PlainTextResponse:
        """Health check for Docker/K8s."""
        return PlainTextResponse("ok")

    return mcp


async def startup() -> None:
    """
    Run async initialization tasks before server starts.

    Connects to backends and discovers skills.
    """
    settings = get_settings()
    # Skill discovery happens at import time via register_all_tools
    # Backend connections are lazy (connect on first use)
    logger.info(f"🚀 MCP Gateway starting on port {settings.port}")


mcp = create_server()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=get_settings().port)
```

**Dependencies**: `fastmcp`, `starlette` (bundled with fastmcp), `mcp_gateway.config`, `mcp_gateway.tools`, `mcp_gateway.skills.registry`, `mcp_gateway.backends.search_backend`, `mcp_gateway.middleware.*`

---

#### `src/mcp_gateway/config.py` -- Pydantic Settings

**Purpose**: Centralized configuration loaded from environment variables with `MCP_GATEWAY_` prefix.

```python
"""
MCP Gateway configuration.

All settings loaded from environment variables with MCP_GATEWAY_ prefix.
"""

import functools

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPGatewaySettings(BaseSettings):
    """
    MCP Gateway settings loaded from environment.

    Attributes:
        port: HTTP server port.
        host: HTTP server bind address.
        log_level: Logging level.
        skills_dir: Path to skills directory containing SKILL.md files.
        qdrant_host: Qdrant server hostname.
        qdrant_port: Qdrant REST API port.
        embedder_host: Embedder gRPC service hostname.
        embedder_port: Embedder gRPC service port.
        db_url: PostgreSQL async connection URL.
        skill_default_timeout: Default subprocess timeout in seconds.
        skill_default_max_output: Default max stdout bytes.
    """

    port: int = Field(8100, description="HTTP server port")
    host: str = Field("0.0.0.0", description="HTTP server bind address")
    log_level: str = Field("INFO", description="Logging level")
    skills_dir: str = Field("/app/skills", description="Skills directory path")
    qdrant_host: str = Field("qdrant", description="Qdrant hostname")
    qdrant_port: int = Field(6333, description="Qdrant REST port")
    embedder_host: str = Field("embedder", description="Embedder gRPC host")
    embedder_port: int = Field(50051, description="Embedder gRPC port")
    db_url: str = Field(
        "postgresql+asyncpg://echomind:echomind@postgres:5432/echomind",
        description="PostgreSQL async URL",
    )
    skill_default_timeout: int = Field(30, description="Default skill timeout (seconds)")
    skill_default_max_output: int = Field(65536, description="Default max output bytes")

    model_config = SettingsConfigDict(
        env_prefix="MCP_GATEWAY_",
        env_file=".env",
    )


@functools.lru_cache
def get_settings() -> MCPGatewaySettings:
    """
    Get cached settings singleton.

    Returns:
        MCPGatewaySettings instance.
    """
    return MCPGatewaySettings()
```

**Dependencies**: `pydantic`, `pydantic-settings`

---

#### `src/mcp_gateway/tools/__init__.py` -- Tool Registration

**Purpose**: Register all tool functions on the FastMCP instance.

```python
"""
Tool registration module.

Registers all MCP tools from each namespace onto the FastMCP server.
"""

from fastmcp import FastMCP

from mcp_gateway.backends.search_backend import SearchBackend
from mcp_gateway.skills.registry import SkillRegistry
from mcp_gateway.tools.search import register_search_tools
from mcp_gateway.tools.skills import register_skill_tools


def register_all_tools(
    mcp: FastMCP,
    search_backend: SearchBackend,
    skill_registry: SkillRegistry,
) -> None:
    """
    Register all tool namespaces on the MCP server.

    Args:
        mcp: FastMCP server instance.
        search_backend: Initialized search backend.
        skill_registry: Initialized skill registry.
    """
    register_search_tools(mcp, search_backend)
    register_skill_tools(mcp, skill_registry)
```

---

#### `src/mcp_gateway/tools/search.py` -- Search Tools

**Purpose**: MCP tool functions for semantic search over Qdrant collections.

```python
"""
Search MCP tools.

Exposes semantic search over Qdrant vector collections.
"""

import logging

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from mcp_gateway.backends.search_backend import SearchBackend

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    """A document chunk from vector search."""

    document_id: int = Field(..., description="Document database ID")
    chunk_id: str = Field(..., description="Chunk identifier within document")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Chunk text content")
    score: float = Field(..., description="Similarity score (0-1)")
    source_url: str | None = Field(None, description="Original source URL")
    connector_type: str | None = Field(None, description="Data source type")


class CollectionInfo(BaseModel):
    """Qdrant collection metadata."""

    name: str = Field(..., description="Collection name")
    vectors_count: int = Field(..., description="Number of vectors")
    points_count: int = Field(..., description="Number of points")
    status: str = Field(..., description="Collection status")


def register_search_tools(mcp: FastMCP, backend: SearchBackend) -> None:
    """
    Register search tools on the MCP server.

    Args:
        mcp: FastMCP server instance.
        backend: Search backend for Qdrant + Embedder.
    """

    @mcp.tool
    async def search_documents(
        ctx: Context,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.5,
    ) -> list[SearchResult]:
        """
        Search documents using semantic similarity.

        Embeds the query via Embedder gRPC, searches across Qdrant
        collections, and returns ranked document chunks.

        Args:
            ctx: FastMCP context.
            query: Natural language search query.
            limit: Maximum results to return.
            score_threshold: Minimum similarity score (0-1).

        Returns:
            Ranked list of matching document chunks.
        """
        await ctx.info(f"Searching for: {query}")
        results = await backend.search(
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )
        await ctx.info(f"Found {len(results)} results")
        return [SearchResult(**r) for r in results]

    @mcp.tool
    async def search_collections(ctx: Context) -> list[CollectionInfo]:
        """
        List available Qdrant collections with statistics.

        Returns:
            List of collections with vector counts and status.
        """
        collections = await backend.list_collections()
        return [CollectionInfo(**c) for c in collections]

    @mcp.tool
    async def get_document(ctx: Context, document_id: int) -> dict:
        """
        Get document metadata by ID.

        Args:
            ctx: FastMCP context.
            document_id: Document database ID.

        Returns:
            Document metadata (title, source, type, dates).
        """
        return await backend.get_document(document_id)

    @mcp.tool
    async def get_document_chunks(
        ctx: Context,
        document_id: int,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get all chunks for a document.

        Use after search to read full document content.

        Args:
            ctx: FastMCP context.
            document_id: Document database ID.
            limit: Maximum chunks to return.

        Returns:
            List of chunk dicts with content and metadata.
        """
        return await backend.get_document_chunks(document_id, limit=limit)
```

**Dependencies**: `fastmcp`, `pydantic`, `mcp_gateway.backends.search_backend`

---

#### `src/mcp_gateway/tools/skills.py` -- Skills Tools

**Purpose**: MCP tool functions for skill discovery, info retrieval, and execution.

```python
"""
Skills MCP tools.

Exposes SKILL.md-based bash skills: list, get info, execute.
"""

import logging

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from mcp_gateway.skills.executor import SkillExecutor
from mcp_gateway.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillInfo(BaseModel):
    """Compact skill metadata for listing."""

    name: str = Field(..., description="Skill identifier")
    description: str = Field(..., description="What the skill does")
    parameters: list[dict] = Field(default_factory=list, description="Expected parameters")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class SkillDetailInfo(BaseModel):
    """Full skill info including instructions body."""

    name: str = Field(..., description="Skill identifier")
    description: str = Field(..., description="What the skill does")
    parameters: list[dict] = Field(default_factory=list, description="Expected parameters")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    instructions: str = Field(..., description="Full SKILL.md body with usage examples")


class SkillExecuteResult(BaseModel):
    """Result of skill execution."""

    success: bool = Field(..., description="True if exit code was 0")
    output: str = Field(..., description="Combined stdout/stderr output")
    exit_code: int = Field(..., description="Process exit code")
    duration_ms: int = Field(..., description="Execution time in milliseconds")


def register_skill_tools(mcp: FastMCP, registry: SkillRegistry) -> None:
    """
    Register skill tools on the MCP server.

    Args:
        mcp: FastMCP server instance.
        registry: Skill registry with discovered skills.
    """
    executor = SkillExecutor()

    @mcp.tool
    async def skills_list(ctx: Context) -> list[SkillInfo]:
        """
        List all available skills with names, descriptions, and parameters.

        Returns compact metadata. Call skills_get_info for full instructions.

        Returns:
            List of available skills.
        """
        skills = registry.list_skills()
        return [
            SkillInfo(
                name=s.name,
                description=s.description,
                parameters=s.parameters,
                tags=s.tags,
            )
            for s in skills
        ]

    @mcp.tool
    async def skills_get_info(ctx: Context, skill_name: str) -> SkillDetailInfo:
        """
        Get detailed information about a skill including full instructions.

        Call this before skills_execute to learn the skill's bash patterns
        and usage examples.

        Args:
            ctx: FastMCP context.
            skill_name: Skill identifier from skills_list.

        Returns:
            Full skill info with instructions body.
        """
        skill = registry.get_skill(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name}")

        return SkillDetailInfo(
            name=skill.name,
            description=skill.description,
            parameters=skill.parameters,
            tags=skill.tags,
            instructions=skill.instructions,
        )

    @mcp.tool
    async def skills_execute(
        ctx: Context,
        skill_name: str,
        command: str,
    ) -> SkillExecuteResult:
        """
        Execute a bash command in the context of a skill.

        The command runs in an isolated subprocess with timeout and
        output size limits. Use skills_get_info first to learn which
        bash commands are appropriate for the skill.

        Args:
            ctx: FastMCP context.
            skill_name: Skill to execute within.
            command: Bash command string to run.

        Returns:
            Execution result with output, exit code, and duration.
        """
        skill = registry.get_skill(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name}")

        await ctx.info(f"Executing skill '{skill_name}': {command[:100]}")

        result = await executor.execute(
            skill=skill,
            command=command,
        )

        await ctx.info(
            f"Skill '{skill_name}' completed: exit_code={result.exit_code}, "
            f"duration={result.duration_ms}ms"
        )

        return SkillExecuteResult(
            success=result.success,
            output=result.output,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
        )
```

**Dependencies**: `fastmcp`, `pydantic`, `mcp_gateway.skills.registry`, `mcp_gateway.skills.executor`

---

#### `src/mcp_gateway/skills/registry.py` -- SkillRegistry

**Purpose**: Parse SKILL.md files from disk, cache SkillDefinition objects, provide fast lookup.

```python
"""
Skill registry -- SKILL.md parser and discovery.

Scans a directory for SKILL.md files with YAML frontmatter,
parses them into SkillDefinition objects, and caches them.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS: int = 30
DEFAULT_MAX_OUTPUT_BYTES: int = 65_536


@dataclass
class SkillDefinition:
    """
    Parsed SKILL.md definition.

    Attributes:
        name: Skill identifier (directory name or frontmatter name).
        description: One-line description.
        parameters: List of parameter dicts with name, description, required, default.
        tags: Categorization tags.
        instructions: Full markdown body from SKILL.md.
        timeout_seconds: Max subprocess execution time.
        max_output_bytes: Max stdout capture size.
        skill_dir: Absolute path to the skill directory.
    """

    name: str
    description: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    instructions: str = ""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    skill_dir: str = ""


class SkillRegistry:
    """
    Discovers and caches skills from filesystem.

    Scans a directory tree for SKILL.md files, parses YAML
    frontmatter + markdown body, and provides fast lookup.
    """

    # Regex to split YAML frontmatter from body
    _FRONTMATTER_RE = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)",
        re.DOTALL,
    )

    def __init__(self, skills_dir: str) -> None:
        """
        Initialize registry.

        Args:
            skills_dir: Path to directory containing skill subdirectories.
        """
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}

    async def discover(self) -> None:
        """
        Scan skills directory and parse all SKILL.md files.

        Logs warnings for unparseable skills but does not raise.
        """
        if not self._skills_dir.exists():
            logger.warning(f"⚠️ Skills directory not found: {self._skills_dir}")
            return

        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                skill = self._parse_skill_md(skill_dir.name, skill_md, skill_dir)
                self._skills[skill.name] = skill
                logger.info(f"🔧 Discovered skill: {skill.name}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse skill {skill_dir.name}: {e}")

        logger.info(f"🔧 Discovered {len(self._skills)} skills total")

    def list_skills(self) -> list[SkillDefinition]:
        """Return all discovered skills."""
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillDefinition | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    @property
    def skill_count(self) -> int:
        """Return number of discovered skills."""
        return len(self._skills)

    def _parse_skill_md(
        self,
        dir_name: str,
        path: Path,
        skill_dir: Path,
    ) -> SkillDefinition:
        """
        Parse a SKILL.md file into a SkillDefinition.

        Args:
            dir_name: Skill directory name (fallback identifier).
            path: Path to SKILL.md file.
            skill_dir: Path to skill directory.

        Returns:
            Populated SkillDefinition.

        Raises:
            ValueError: If description is missing.
        """
        content = path.read_text(encoding="utf-8")

        match = self._FRONTMATTER_RE.match(content)
        if not match:
            raise ValueError(
                f"SKILL.md must have YAML frontmatter delimited by ---"
            )

        frontmatter_str = match.group(1)
        body = match.group(2).strip()

        meta = yaml.safe_load(frontmatter_str) or {}

        name = meta.get("name", dir_name)
        description = meta.get("description")
        if not description:
            raise ValueError(f"SKILL.md must have a 'description' field")

        return SkillDefinition(
            name=name,
            description=description,
            parameters=meta.get("parameters", []),
            tags=meta.get("tags", []),
            instructions=body,
            timeout_seconds=meta.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            max_output_bytes=meta.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES),
            skill_dir=str(skill_dir.resolve()),
        )
```

**Dependencies**: `pyyaml`, standard library (`re`, `pathlib`, `dataclasses`, `logging`)

---

#### `src/mcp_gateway/skills/executor.py` -- SkillExecutor

**Purpose**: Run bash commands in isolated subprocesses with timeout and output limits.

```python
"""
Skill executor -- subprocess execution with resource limits.

Runs bash commands in isolated subprocesses with configurable
timeout, output size limits, and clean environment.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from mcp_gateway.skills.exceptions import SkillTimeoutError
from mcp_gateway.skills.registry import SkillDefinition

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """
    Result of a subprocess execution.

    Attributes:
        success: True if exit code was 0.
        output: Combined stdout/stderr output (truncated to max_output_bytes).
        exit_code: Process exit code.
        duration_ms: Execution time in milliseconds.
    """

    success: bool
    output: str
    exit_code: int
    duration_ms: int


class SkillExecutor:
    """
    Executes bash commands in isolated subprocesses.

    Each execution:
    - Runs in the skill's directory as cwd
    - Has a configurable timeout (default 30s)
    - Captures stdout+stderr up to max_output_bytes
    - Uses a clean environment (PATH only, no leaked secrets)
    """

    # Minimal safe environment for subprocess
    _SAFE_ENV_KEYS: frozenset[str] = frozenset({
        "PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM",
        "SHELL", "TMPDIR",
    })

    async def execute(
        self,
        skill: SkillDefinition,
        command: str,
    ) -> ExecutionResult:
        """
        Execute a bash command in a skill's context.

        Args:
            skill: Skill definition (provides cwd, timeout, output limits).
            command: Bash command string to execute.

        Returns:
            ExecutionResult with output, exit code, and timing.

        Raises:
            SkillTimeoutError: If execution exceeds skill.timeout_seconds.
        """
        start_time = time.monotonic()

        # Build clean environment (no leaked API keys or secrets)
        env = {
            k: v for k, v in os.environ.items()
            if k in self._SAFE_ENV_KEYS
        }
        env["SKILL_NAME"] = skill.name

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=skill.skill_dir,
            )

            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=skill.timeout_seconds,
            )

            output = stdout[: skill.max_output_bytes].decode(
                "utf-8", errors="replace"
            )
            duration_ms = int((time.monotonic() - start_time) * 1000)

            logger.info(
                f"🔧 Skill '{skill.name}' executed: "
                f"exit_code={proc.returncode}, duration={duration_ms}ms"
            )

            return ExecutionResult(
                success=proc.returncode == 0,
                output=output,
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                f"⏰ Skill '{skill.name}' timed out after "
                f"{skill.timeout_seconds}s (duration={duration_ms}ms)"
            )
            raise SkillTimeoutError(
                skill_name=skill.name,
                timeout_seconds=skill.timeout_seconds,
                actual_duration_ms=duration_ms,
            ) from None
```

**Dependencies**: standard library (`asyncio`, `os`, `time`, `logging`, `dataclasses`), `mcp_gateway.skills.exceptions`

---

#### `src/mcp_gateway/skills/exceptions.py` -- Skill Exceptions

**Purpose**: Domain exceptions for skill operations.

```python
"""
Skill domain exceptions.

Raised by SkillRegistry and SkillExecutor, caught by
ErrorHandlingMiddleware and mapped to MCP ToolError responses.
"""


class SkillNotFoundError(Exception):
    """Raised when a requested skill does not exist."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillTimeoutError(Exception):
    """Raised when skill execution exceeds the timeout."""

    def __init__(
        self,
        skill_name: str,
        timeout_seconds: int,
        actual_duration_ms: int,
    ) -> None:
        self.skill_name = skill_name
        self.timeout_seconds = timeout_seconds
        self.actual_duration_ms = actual_duration_ms
        super().__init__(
            f"Skill '{skill_name}' timed out after {timeout_seconds}s "
            f"(ran for {actual_duration_ms}ms)"
        )
```

---

#### `src/mcp_gateway/middleware/audit_logger.py` -- Audit Logging Middleware

**Purpose**: Log every MCP tool invocation as structured JSON.

```python
"""
Audit logging middleware.

Logs every tool invocation with structured JSON:
tool name, parameters, result status, duration, errors.
"""

import json
import logging
import time
from datetime import datetime, timezone

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger("mcp_gateway.audit")


class AuditLoggingMiddleware(Middleware):
    """
    Structured JSON audit logger for all MCP tool calls.

    Logs to the 'mcp_gateway.audit' logger at INFO level.
    Each entry includes: timestamp, tool, parameters, status, duration, error.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: object,
    ) -> object:
        """
        Log tool invocation before and after execution.

        Args:
            context: Middleware context with request details.
            call_next: Next handler in middleware chain.

        Returns:
            Tool execution result.
        """
        tool_name = context.message.name
        arguments = context.message.arguments or {}
        start_time = time.monotonic()
        error_msg: str | None = None
        status = "success"

        try:
            result = await call_next(context)
            return result
        except Exception as e:
            status = "error"
            error_msg = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = int((time.monotonic() - start_time) * 1000)

            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "mcp_tool_call",
                "tool": tool_name,
                "parameters": self._redact_sensitive(arguments),
                "result_status": status,
                "duration_ms": duration_ms,
                "error": error_msg,
            }

            logger.info(json.dumps(audit_entry, default=str))

    @staticmethod
    def _redact_sensitive(params: dict) -> dict:
        """
        Redact sensitive parameter values.

        Replaces values for keys containing 'key', 'token',
        'secret', 'password' with '***'.

        Args:
            params: Raw parameter dict.

        Returns:
            Redacted parameter dict.
        """
        sensitive_patterns = {"key", "token", "secret", "password", "credential"}
        redacted = {}
        for k, v in params.items():
            if any(pattern in k.lower() for pattern in sensitive_patterns):
                redacted[k] = "***"
            else:
                redacted[k] = v
        return redacted
```

**Dependencies**: `fastmcp`, standard library (`json`, `time`, `datetime`, `logging`)

---

#### `src/mcp_gateway/middleware/error_handler.py` -- Error Handling Middleware

**Purpose**: Catch domain exceptions and convert them to MCP ToolError responses.

```python
"""
Error handling middleware.

Catches domain exceptions (SkillNotFoundError, SkillTimeoutError, etc.)
and maps them to appropriate MCP ToolError responses.
"""

import logging

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_gateway.skills.exceptions import SkillNotFoundError, SkillTimeoutError

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(Middleware):
    """
    Maps domain exceptions to MCP ToolError responses.

    Catches known exception types and returns user-friendly
    error messages. Unknown exceptions are logged and re-raised.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: object,
    ) -> object:
        """
        Wrap tool execution with error mapping.

        Args:
            context: Middleware context.
            call_next: Next handler in chain.

        Returns:
            Tool execution result.

        Raises:
            ToolError: Mapped from domain exceptions.
        """
        try:
            return await call_next(context)
        except SkillNotFoundError as e:
            raise ToolError(f"Skill not found: {e.skill_name}") from e
        except SkillTimeoutError as e:
            raise ToolError(
                f"Skill '{e.skill_name}' timed out after "
                f"{e.timeout_seconds}s"
            ) from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except ToolError:
            raise  # Already a ToolError, pass through
        except Exception as e:
            logger.exception(f"❌ Unexpected error in tool execution")
            raise ToolError(f"Internal error: {type(e).__name__}") from e
```

**Dependencies**: `fastmcp`, `mcp_gateway.skills.exceptions`

---

#### `src/mcp_gateway/backends/search_backend.py` -- Search Backend

**Purpose**: Integrate with Qdrant (vector search) and Embedder (gRPC for embeddings).

```python
"""
Search backend -- Qdrant + Embedder integration.

Provides semantic search by embedding queries via Embedder gRPC
and searching across Qdrant collections.
"""

import logging
from typing import Any

import grpc
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import SearchParams

from echomind_lib.models.internal.embedding_pb2 import EmbedRequest
from echomind_lib.models.internal.embedding_pb2_grpc import EmbedServiceStub

logger = logging.getLogger(__name__)


class SearchBackend:
    """
    Backend for semantic search operations.

    Manages connections to Qdrant and Embedder services.
    Provides lazy connection initialization (connect on first use).

    Attributes:
        qdrant_host: Qdrant server hostname.
        qdrant_port: Qdrant REST API port.
        embedder_host: Embedder gRPC hostname.
        embedder_port: Embedder gRPC port.
    """

    def __init__(
        self,
        qdrant_host: str,
        qdrant_port: int,
        embedder_host: str,
        embedder_port: int,
    ) -> None:
        """
        Initialize search backend.

        Connections are lazy -- created on first use.

        Args:
            qdrant_host: Qdrant hostname.
            qdrant_port: Qdrant port.
            embedder_host: Embedder gRPC hostname.
            embedder_port: Embedder gRPC port.
        """
        self._qdrant_host = qdrant_host
        self._qdrant_port = qdrant_port
        self._embedder_host = embedder_host
        self._embedder_port = embedder_port
        self._qdrant: AsyncQdrantClient | None = None
        self._embedder_channel: grpc.aio.Channel | None = None
        self._embedder_stub: EmbedServiceStub | None = None

    async def _ensure_qdrant(self) -> AsyncQdrantClient:
        """
        Ensure Qdrant client is initialized.

        Returns:
            Connected AsyncQdrantClient.
        """
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(
                host=self._qdrant_host,
                port=self._qdrant_port,
                prefer_grpc=True,
            )
            logger.info(
                f"🔗 Connected to Qdrant at "
                f"{self._qdrant_host}:{self._qdrant_port}"
            )
        return self._qdrant

    async def _ensure_embedder(self) -> EmbedServiceStub:
        """
        Ensure Embedder gRPC stub is initialized.

        Returns:
            Connected EmbedServiceStub.
        """
        if self._embedder_stub is None:
            target = f"{self._embedder_host}:{self._embedder_port}"
            self._embedder_channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", 10 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 10 * 1024 * 1024),
                ],
            )
            self._embedder_stub = EmbedServiceStub(self._embedder_channel)
            logger.info(f"🔗 Connected to Embedder at {target}")
        return self._embedder_stub

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a query string via Embedder gRPC.

        Args:
            query: Text to embed.

        Returns:
            Embedding vector.

        Raises:
            RuntimeError: If Embedder is unavailable.
        """
        stub = await self._ensure_embedder()
        try:
            request = EmbedRequest(texts=[query])
            response = await stub.Embed(request, timeout=30.0)
            if not response.embeddings:
                raise RuntimeError("Embedder returned empty response")
            return list(response.embeddings[0].vector)
        except grpc.aio.AioRpcError as e:
            logger.error(f"❌ Embedder gRPC error: {e.details()}")
            raise RuntimeError(f"Embedder unavailable: {e.details()}") from e

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.5,
        collections: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search across Qdrant collections.

        Embeds the query, searches each collection, merges and
        ranks results by score.

        Args:
            query: Natural language search query.
            limit: Maximum results.
            score_threshold: Minimum similarity score.
            collections: Specific collections to search (None = all).

        Returns:
            Ranked list of result dicts.
        """
        qdrant = await self._ensure_qdrant()
        query_vector = await self.embed_query(query)

        # Get target collections
        if collections is None:
            collection_list = await qdrant.get_collections()
            target_collections = [c.name for c in collection_list.collections]
        else:
            target_collections = collections

        # Search each collection
        all_results: list[dict[str, Any]] = []
        for collection_name in target_collections:
            try:
                results = await qdrant.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    search_params=SearchParams(hnsw_ef=128, exact=False),
                )
                for r in results:
                    payload = r.payload or {}
                    all_results.append({
                        "document_id": payload.get("document_id", 0),
                        "chunk_id": str(r.id),
                        "title": payload.get("title", ""),
                        "content": payload.get("content", ""),
                        "score": r.score,
                        "source_url": payload.get("source_url"),
                        "connector_type": payload.get("connector_type"),
                    })
            except Exception as e:
                logger.warning(
                    f"⚠️ Search failed for collection '{collection_name}': {e}"
                )
                continue

        # Sort by score descending, take top N
        all_results.sort(key=lambda r: r["score"], reverse=True)
        return all_results[:limit]

    async def list_collections(self) -> list[dict[str, Any]]:
        """
        List all Qdrant collections with stats.

        Returns:
            List of collection info dicts.
        """
        qdrant = await self._ensure_qdrant()
        collection_list = await qdrant.get_collections()
        result: list[dict[str, Any]] = []
        for c in collection_list.collections:
            try:
                info = await qdrant.get_collection(c.name)
                result.append({
                    "name": c.name,
                    "vectors_count": info.vectors_count or 0,
                    "points_count": info.points_count or 0,
                    "status": info.status.value,
                })
            except Exception as e:
                logger.warning(f"⚠️ Failed to get info for collection '{c.name}': {e}")
        return result

    async def get_document(self, document_id: int) -> dict[str, Any]:
        """
        Get document metadata by ID.

        Queries Qdrant for points with matching document_id payload.

        Args:
            document_id: Document database ID.

        Returns:
            Document metadata dict.

        Raises:
            ValueError: If document not found.
        """
        # TODO: Query PostgreSQL for document metadata once DB integration is added
        # For now, search Qdrant for any chunk with this document_id
        raise ValueError(
            f"Document lookup by ID not yet implemented. "
            f"Use search_documents instead. (document_id={document_id})"
        )

    async def get_document_chunks(
        self,
        document_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get all chunks for a document.

        Args:
            document_id: Document database ID.
            limit: Maximum chunks.

        Returns:
            List of chunk dicts.

        Raises:
            ValueError: If document not found.
        """
        # TODO: Query Qdrant with document_id filter once payload indexing is confirmed
        raise ValueError(
            f"Document chunk retrieval not yet implemented. "
            f"Use search_documents instead. (document_id={document_id})"
        )

    async def close(self) -> None:
        """Close all backend connections."""
        if self._qdrant:
            await self._qdrant.close()
            self._qdrant = None
        if self._embedder_channel:
            await self._embedder_channel.close()
            self._embedder_channel = None
            self._embedder_stub = None
        logger.info("🔗 Search backend connections closed")
```

**Dependencies**: `qdrant-client`, `grpcio`, `echomind_lib.models.internal.embedding_pb2`, `echomind_lib.models.internal.embedding_pb2_grpc`

---

#### `src/mcp_gateway/Dockerfile` -- Multi-stage Build

```dockerfile
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

COPY src/mcp_gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy shared library
COPY src/echomind_lib /app/echomind_lib

# Copy MCP gateway source
COPY src/mcp_gateway /app/mcp_gateway

# Copy skills
COPY skills /app/skills

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd -m -u 1000 mcpuser
USER mcpuser

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8100/healthz || exit 1

CMD ["python", "-m", "mcp_gateway.main"]
```

---

#### `src/mcp_gateway/requirements.txt` -- Pinned Dependencies

```
# MCP framework
fastmcp==2.14.5

# Pydantic settings
pydantic>=2.0,<3.0
pydantic-settings>=2.0,<3.0

# Vector database
qdrant-client>=1.12.0,<2.0

# gRPC for Embedder
grpcio>=1.67.1,<2.0
protobuf>=5.28.0,<6.0

# YAML parsing for SKILL.md
pyyaml>=6.0,<7.0

# Database (for Phase 2 connector tools)
# sqlalchemy[asyncio]>=2.0,<3.0
# asyncpg>=0.30,<1.0
```

---

## Docker Compose Service Definition

```yaml
# Add to docker-compose.yml
services:
  echomind-mcp:
    build:
      context: .
      dockerfile: src/mcp_gateway/Dockerfile
    container_name: echomind-mcp
    ports:
      - "8100:8100"
    environment:
      - MCP_GATEWAY_PORT=8100
      - MCP_GATEWAY_LOG_LEVEL=INFO
      - MCP_GATEWAY_SKILLS_DIR=/app/skills
      - MCP_GATEWAY_QDRANT_HOST=qdrant
      - MCP_GATEWAY_QDRANT_PORT=6333
      - MCP_GATEWAY_EMBEDDER_HOST=embedder
      - MCP_GATEWAY_EMBEDDER_PORT=50051
      - MCP_GATEWAY_DB_URL=${API_DB_URL:-postgresql+asyncpg://echomind:echomind@postgres:5432/echomind}
    volumes:
      - ./skills:/app/skills:ro
    networks:
      - backend
      - sandbox
    depends_on:
      - qdrant
      - embedder
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
    restart: unless-stopped
```

### Network Configuration

```yaml
networks:
  backend:
    # Existing network for PostgreSQL, Qdrant, Embedder, API
  sandbox:
    # New network for sandbox containers + MCP gateway
    # Sandboxes can reach MCP gateway but NOT PostgreSQL/Qdrant directly
```

The MCP gateway sits on both `backend` (to reach Qdrant, Embedder, PostgreSQL) and `sandbox` (to be reachable from sandbox containers).

---

## Deployment & Operations

### Streamable HTTP Transport

The gateway uses FastMCP's HTTP transport mode. Agent containers connect to `http://echomind-mcp:8100/mcp`:

```python
# In the gateway main.py
from fastmcp import FastMCP

mcp = FastMCP("EchoMind Gateway")

# Register all tools...

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8100)
```

### Agent Config Integration

```yaml
# config/agents/config.yaml (updated)
mcpServers:
  - name: echomind-gateway
    transport: http
    url: "http://echomind-mcp:8100/mcp"
    approvalMode: never_require  # Gateway handles its own approval
    requestTimeout: 30

agents:
  list:
    - id: assistant
      name: "EchoMind Assistant"
      model: "${OPENAI_MODEL:-gpt-4o-mini}"
      mcpServers: ["echomind-gateway"]
      instructions: |
        You have access to the following capabilities via MCP tools:
        - search_documents: Search the user's knowledge base
        - skills_list/skills_get_info/skills_execute: Discover and run bash skills
        Use these tools to help the user. Never ask for API keys or credentials.
```

### Scaling

| Load Level | Strategy |
|------------|----------|
| Single instance | 1 gateway, handles ~100 concurrent agent sessions |
| Medium (100-500 sessions) | 2-3 replicas behind internal load balancer |
| High (500+) | Horizontal scaling + Redis for shared state |

The gateway is stateless. Scaling is straightforward with Docker replicas.

### Health Checks

The `/healthz` endpoint is a custom HTTP route (not an MCP tool). It returns `200 OK` with body `"ok"` when the server is running. Future phases will add backend connectivity checks following the EchoMind resilience pattern (`.claude/rules/resilience.md`).

### Verification

```bash
# Start gateway locally
PYTHONPATH=src MCP_GATEWAY_SKILLS_DIR=./skills python -m mcp_gateway.main

# Test health check
curl http://localhost:8100/healthz

# Test with MCP client
python -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8100/mcp') as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f'{len(tools.tools)} tools available')
            for t in tools.tools:
                print(f'  - {t.name}: {t.description[:60]}')

asyncio.run(test())
"
```

---

## Integration with Existing Agent System

### What Changes in the Agent System

1. **`MCPManager` (no changes needed)** -- Already supports HTTP transport. Just add the gateway to `config.yaml`.

2. **`MCPServerConfig` (no changes needed)** -- HTTP URL and headers dict already supported.

3. **`config.yaml` (update)** -- Add `echomind-gateway` MCP server definition. Reference it in agent `mcpServers` lists.

### What the Gateway Reuses from Existing Code

| Component | Source | How Used |
|-----------|--------|----------|
| `QdrantDB` | `src/echomind_lib/db/qdrant.py` | Vector search backend (pattern reference) |
| `EmbedderClient` | `src/api/logic/embedder_client.py` | Query embedding (pattern reference) |
| Proto models | `src/echomind_lib/models/internal/` | `EmbedRequest`, `EmbedServiceStub` |

In Phase 1, the search backend directly uses `qdrant-client` and `grpcio` rather than importing `QdrantDB` and `EmbedderClient` classes. This avoids pulling in database dependencies not yet needed. The implementations follow the same patterns as the existing code.

### Dependency Graph

```
echomind-mcp (MCP Gateway)
  depends on:
    echomind_lib (shared library)
      - models/internal/embedding_pb2.py
      - models/internal/embedding_pb2_grpc.py
    fastmcp >= 2.14
    qdrant-client
    grpcio
    pydantic, pydantic-settings
    pyyaml
```

---

## Dependencies

| Package | Version | Justification |
|---------|---------|---------------|
| `fastmcp` | `==2.14.5` | MCP framework. Stable release with all needed features (tools, middleware, HTTP transport, custom routes). Upgrade to 3.0 when stable. |
| `pydantic` | `>=2.0,<3.0` | Tool parameter/return validation. Required by FastMCP. |
| `pydantic-settings` | `>=2.0,<3.0` | Environment-based configuration with `MCP_GATEWAY_` prefix. |
| `qdrant-client` | `>=1.12.0,<2.0` | Async Qdrant client for vector search. Matches version used by other EchoMind services. |
| `grpcio` | `>=1.67.1,<2.0` | Embedder gRPC client. Pinned to 1.67.1+ for proto compatibility (see MEMORY.md). |
| `protobuf` | `>=5.28.0,<6.0` | Protobuf runtime for generated models. |
| `pyyaml` | `>=6.0,<7.0` | YAML frontmatter parsing for SKILL.md files. |

### Phase 2+ Additions

| Package | Version | When |
|---------|---------|------|
| `sqlalchemy[asyncio]` | `>=2.0,<3.0` | Phase 2 (connector tools) |
| `asyncpg` | `>=0.30,<1.0` | Phase 2 (PostgreSQL backend) |
| `pyjwt[crypto]` | `>=2.8,<3.0` | Phase 8 (JWT auth) |

---

## Test Plan

### Unit Tests (`tests/unit/mcp_gateway/`)

#### `test_config.py` -- Settings Tests (~5 tests)

| Test | Description |
|------|-------------|
| `test_default_settings` | All defaults load without env vars |
| `test_env_prefix` | Settings read from `MCP_GATEWAY_*` env vars |
| `test_custom_port` | Port overridden via `MCP_GATEWAY_PORT` |
| `test_custom_skills_dir` | Skills dir overridden via env |
| `test_settings_cached` | `get_settings()` returns same instance |

#### `test_skill_registry.py` -- Skill Discovery Tests (~10 tests)

| Test | Description |
|------|-------------|
| `test_discover_skills` | Finds all SKILL.md files in directory |
| `test_discover_empty_dir` | Handles empty skills directory |
| `test_discover_missing_dir` | Logs warning for missing directory |
| `test_parse_frontmatter` | Parses YAML frontmatter correctly |
| `test_parse_body` | Extracts markdown body as instructions |
| `test_missing_description` | Raises ValueError for missing description |
| `test_missing_frontmatter` | Raises ValueError for no `---` delimiters |
| `test_default_timeout` | Falls back to 30s when not specified |
| `test_custom_timeout` | Reads timeout_seconds from frontmatter |
| `test_list_skills` | Returns all discovered skills |
| `test_get_skill_found` | Returns skill by name |
| `test_get_skill_not_found` | Returns None for unknown skill |

#### `test_skill_executor.py` -- Subprocess Tests (~8 tests)

| Test | Description |
|------|-------------|
| `test_execute_success` | Simple command returns success, output, exit_code=0 |
| `test_execute_failure` | Failing command returns exit_code != 0 |
| `test_execute_timeout` | Raises SkillTimeoutError after timeout_seconds |
| `test_execute_output_truncation` | Output capped at max_output_bytes |
| `test_clean_environment` | Subprocess gets only safe env vars |
| `test_cwd_set_to_skill_dir` | Subprocess runs in skill directory |
| `test_execute_stderr_merged` | stderr captured alongside stdout |
| `test_duration_tracking` | duration_ms is populated correctly |

#### `test_audit_middleware.py` -- Audit Logging Tests (~5 tests)

| Test | Description |
|------|-------------|
| `test_logs_success` | Logs JSON with status=success for passing tool |
| `test_logs_error` | Logs JSON with status=error and error message |
| `test_redacts_sensitive` | Redacts keys containing 'token', 'key', 'secret' |
| `test_includes_duration` | duration_ms is populated |
| `test_includes_tool_name` | tool name present in log entry |

#### `test_error_middleware.py` -- Error Handling Tests (~5 tests)

| Test | Description |
|------|-------------|
| `test_skill_not_found_error` | Maps SkillNotFoundError to ToolError |
| `test_skill_timeout_error` | Maps SkillTimeoutError to ToolError |
| `test_value_error` | Maps ValueError to ToolError |
| `test_tool_error_passthrough` | ToolError passes through unchanged |
| `test_unexpected_error` | Unknown exception logged and mapped |

#### `test_search_backend.py` -- Search Backend Tests (~6 tests)

| Test | Description |
|------|-------------|
| `test_embed_query` | Calls Embedder gRPC and returns vector |
| `test_embed_query_error` | Raises RuntimeError on gRPC failure |
| `test_search_single_collection` | Searches one collection, returns results |
| `test_search_multi_collection` | Merges and ranks results across collections |
| `test_search_collection_error` | Skips failed collections gracefully |
| `test_list_collections` | Returns collection stats |

#### `test_tools_search.py` -- Search Tool Integration (~4 tests)

| Test | Description |
|------|-------------|
| `test_search_documents` | End-to-end tool call with mocked backend |
| `test_search_collections` | Returns collection list |
| `test_get_document` | Returns document metadata (when implemented) |
| `test_get_document_chunks` | Returns chunks (when implemented) |

#### `test_tools_skills.py` -- Skill Tool Integration (~5 tests)

| Test | Description |
|------|-------------|
| `test_skills_list` | Returns all skills from registry |
| `test_skills_get_info_found` | Returns full skill with instructions |
| `test_skills_get_info_not_found` | Raises ValueError for unknown skill |
| `test_skills_execute_success` | Executes command and returns result |
| `test_skills_execute_not_found` | Raises ValueError for unknown skill |

### Integration Tests (`tests/integration/mcp_gateway/`)

| Test | Description |
|------|-------------|
| `test_server_starts` | FastMCP server starts on configured port |
| `test_healthz` | `/healthz` returns 200 OK |
| `test_list_tools` | MCP client can list all registered tools |
| `test_skill_flow_e2e` | `skills_list` -> `skills_get_info` -> `skills_execute` full flow |

### Total Test Count: ~48 tests

---

## Evaluation Scorecard

| Criteria | Score (1-10) | Notes |
|----------|-------------|-------|
| **Architectural simplicity** | 9 | Removing auth makes Phase 1 dramatically simpler. Single FastMCP server, two tool namespaces, audit-only middleware. |
| **Framework fit** | 8 | FastMCP 2.14 provides all needed features. 3.0 RC is close but not yet stable. Middleware, tools, HTTP transport all work out of the box. |
| **Existing code reuse** | 7 | Reuses proto models and follows QdrantDB/EmbedderClient patterns. Full PermissionChecker integration deferred to Phase 8. |
| **Skill system design** | 9 | SKILL.md with YAML frontmatter + markdown body is clean. Progressive disclosure (list -> info -> execute) mirrors Moltbot's proven pattern. |
| **Testability** | 8 | All backends injected, middleware composable, skills use filesystem fixtures. 48 planned tests cover all code paths. |
| **Security posture** | 5 | Intentionally minimal for Phase 1. Network isolation only. Acceptable for development; must be hardened before production (Phase 8). |
| **Operational readiness** | 7 | Health check, Docker Compose, structured logging all included. Missing: Langfuse tracing (Phase 6), resilience retries (future). |

**Overall: 7.6/10** -- Strong foundation for iterative development. Auth and observability are well-defined for later phases.

---

## Citations and Sources

- [FastMCP Documentation -- gofastmcp.com](https://gofastmcp.com) -- Primary reference for FastMCP API, middleware, tools, and transport configuration. [Source -- 2026-02-16]
- [FastMCP GitHub -- jlowin/fastmcp](https://github.com/jlowin/fastmcp) -- Source code, releases, and changelog. v2.14.5 stable, v3.0.0rc2 pre-release. [Source -- 2026-02-14]
- [FastMCP PyPI -- pypi.org/project/fastmcp](https://pypi.org/project/fastmcp/) -- Package versions and dependencies. Latest stable: 2.14.5 (2026-02-03). [Source -- 2026-02-16]
- [FastMCP 3.0 Blog Post -- jlowin.dev](https://www.jlowin.dev/blog/fastmcp-3) -- Architecture overview of 3.0: components, providers, transforms. [Source -- 2026-02-16]
- [FastMCP Middleware Blog -- jlowin.dev](https://www.jlowin.dev/blog/fastmcp-2-9-middleware) -- Middleware system design, `on_call_tool` hooks, `MiddlewareContext`. [Source -- 2026-02-16]
- [FastMCP Running Server Docs](https://gofastmcp.com/deployment/running-server) -- `mcp.run()` API, transport options, `@mcp.custom_route`, ASGI deployment. [Source -- 2026-02-16]
- [FastMCP Context Docs](https://gofastmcp.com/servers/context) -- `Context` injection, logging, progress, session state, `CurrentContext()`. [Source -- 2026-02-16]
- [FastMCP Middleware Docs](https://gofastmcp.com/servers/middleware) -- `Middleware` base class, hooks hierarchy, composition, built-in middleware. [Source -- 2026-02-16]
- [MCP Protocol Specification -- modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) -- Official MCP Python SDK, Streamable HTTP transport spec. [Source -- 2026-02-16]
- [EchoMind Execution Plan](agent_docs/agent_execution-plan.md) -- Phase 1-8 architecture, auth deferral rationale. [Source -- 2026-02-16]
- [EchoMind Resilience Rules](/.claude/rules/resilience.md) -- Connection retry patterns, health probe requirements. [Source -- 2026-02-16]
