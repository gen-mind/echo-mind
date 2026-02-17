# Phase 8: Auth & Security Hardening

> **Date**: 2026-02-17
> **Phase**: 8 of 8 (Sandboxed Agent Architecture)
> **Status**: Ready for review
> **Prerequisites**: Phase 1 (MCP Gateway), Phase 4 (Sandbox Foundation)

---

## 1. Executive Summary

Phase 8 transforms EchoMind's sandbox/MCP architecture from a network-isolation-only security model into a **zero-trust, defense-in-depth system**. Currently, the MCP gateway trusts all callers on the internal Docker network — any container on the sandbox network can invoke any tool without identity verification. This phase adds JWT-based authentication, RBAC enforcement, rate limiting, network hardening, secret management, and a comprehensive audit trail.

### Security Posture: Before vs After

| Dimension | Before (Phase 1-4) | After (Phase 8) |
|-----------|-------------------|-----------------|
| **MCP Authentication** | None — all callers trusted | JWT per sandbox session (RS256, 5min TTL) |
| **Authorization** | None — all tools accessible | Per-tool RBAC via PermissionChecker |
| **Data Scoping** | Search returns all collections | Search scoped to user/team/org collections |
| **Rate Limiting** | None | Per-user + per-session sliding window |
| **Network Isolation** | Sandbox joins backend network | iptables rules restrict sandbox → NATS + MCP only |
| **Secret Storage** | API keys in env vars (plaintext) | Encrypted at rest, rotated signing keys |
| **Audit Trail** | Structured JSON logs (stdout) | DB-persisted security events + NATS audit stream |
| **Token Lifecycle** | N/A | Short-lived (5min), refresh via API, revocation on session end |

### Key Deliverables

1. JWT signing/validation infrastructure in MCP gateway
2. Auth middleware for FastMCP (validates JWT on every tool call)
3. RBAC enforcement using existing `PermissionChecker`
4. Sliding window rate limiter (in-memory, Redis-optional)
5. iptables network hardening for sandbox containers
6. Security audit event table + NATS audit stream
7. JWT signing key rotation table + JWKS endpoint
8. ~60 new unit tests covering auth bypass, expired tokens, permission escalation, rate limits

**Confidence: HIGH** — All auth infrastructure already exists (JWTValidator, PermissionChecker, TokenUser). This phase wires it into the MCP gateway.

---

## 2. Threat Model

### Attack Surface Diagram

```
                             INTERNET
                                |
                            [Traefik] ─── TLS termination
                             /      \
                       [WebUI]    [API :8000] ─── Authentik OIDC
                                     |
                    +----------------+----------------+
                    |                |                |
                 [NATS]          [Postgres]       [Redis]
                    |
       +------------+------------+
       |            |            |
  [sandbox-0]  [sandbox-1]  [sandbox-N]
       |            |            |
       +------+-----+------+
              |             |
    ┌─────────────────┐   [Internet]
    │  MCP Gateway    │   (web search)
    │  ──────────────│
    │  ATTACK VECTORS:│
    │  ① No auth      │ ← Phase 8 fixes
    │  ② No RBAC      │ ← Phase 8 fixes
    │  ③ No rate limit│ ← Phase 8 fixes
    │  ④ Flat network │ ← Phase 8 fixes
    └────────┬────────┘
        ┌────┴────┐
     [Qdrant] [PG] [MinIO]
```

### Risk Matrix

| # | Threat | Attack Vector | Likelihood | Impact | Risk | Mitigation |
|---|--------|--------------|------------|--------|------|------------|
| T1 | **MCP Tool Abuse** | Compromised sandbox calls tools without auth | HIGH | HIGH | **CRITICAL** | JWT validation on every tool call |
| T2 | **Cross-User Data Access** | Sandbox searches another user's collections | MEDIUM | HIGH | **HIGH** | RBAC-scoped search via PermissionChecker |
| T3 | **Data Exfiltration** | Sandbox bulk-extracts documents via MCP | MEDIUM | HIGH | **HIGH** | Rate limiting + audit logging |
| T4 | **Sandbox Escape** | Container breakout via kernel vuln | LOW | CRITICAL | **HIGH** | Read-only FS, no caps, PID limit, gVisor (future) |
| T5 | **NATS Injection** | Sandbox publishes to unauthorized subjects | MEDIUM | MEDIUM | **MEDIUM** | NATS auth + subject ACLs (future) |
| T6 | **Token Theft** | JWT stolen from sandbox container | LOW | HIGH | **MEDIUM** | Short TTL (5min), token binding, revocation |
| T7 | **Denial of Service** | Sandbox floods MCP with tool calls | MEDIUM | MEDIUM | **MEDIUM** | Per-session + per-user rate limiting |
| T8 | **Privilege Escalation** | User manipulates JWT claims | LOW | HIGH | **MEDIUM** | RS256 asymmetric signing, server-side validation |
| T9 | **Network Lateral Movement** | Sandbox reaches Postgres/Qdrant directly | MEDIUM | HIGH | **HIGH** | iptables DOCKER-USER rules |
| T10 | **API Key Exposure** | Sandbox extracts keys from MCP gateway | LOW | HIGH | **MEDIUM** | Keys never in tool responses, clean subprocess env |

[OWASP API Security Top 10 2023 — https://owasp.org/API-Security/editions/2023/en/0x11-t10/]

---

## 3. JWT Authentication Flow

### 3.1 End-to-End Token Flow

```
User                WebUI              API               Authentik          MCP Gateway       Sandbox
 |                   |                  |                    |                  |                |
 |── Login ─────────>|── OIDC redirect ─>|                    |                  |                |
 |                   |                  |── Auth code ──────>|                  |                |
 |                   |                  |<── Access token ───|                  |                |
 |                   |                  |                    |                  |                |
 |── "Ask question" >|── WS message ───>|                    |                  |                |
 |                   |                  |                    |                  |                |
 |                   |                  |── Sign sandbox JWT ────────────────────────────────>  |
 |                   |                  |   (claims: sub, user_id, session_id,                  |
 |                   |                  |    org_id, permissions, exp=5min)                     |
 |                   |                  |                    |                  |                |
 |                   |                  |── Inject JWT env ──────────────────────────────────>  |
 |                   |                  |                    |                  |                |
 |                   |                  |                    |                  |  ← MCP call ──|
 |                   |                  |                    |                  |    + JWT       |
 |                   |                  |                    |                  |── Validate ──>|
 |                   |                  |                    |                  |   Extract      |
 |                   |                  |                    |                  |   claims       |
 |                   |                  |                    |                  |── Check RBAC ─>|
 |                   |                  |                    |                  |── Rate limit ─>|
 |                   |                  |                    |                  |── Execute ────>|
 |                   |                  |                    |                  |                |
 |                   |                  |                    |                  |  ← Response ──|
 |<── Agent reply ──|<── WS stream ───|<── NATS stream ────────────────────── |<── NATS ──────|
```

### 3.2 Token Design

**Algorithm**: RS256 (RSA 2048-bit + SHA-256)

**Rationale**: RS256 is the standard for distributed systems where the verifier (MCP gateway) should not possess the signing key. The API signs tokens; the MCP gateway only needs the public key to verify. This is the same algorithm used by Authentik for OIDC tokens.

[RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens — https://datatracker.ietf.org/doc/html/rfc9068]
[RFC 7519 — JSON Web Token (JWT) — https://datatracker.ietf.org/doc/html/rfc7519]

**Confidence: HIGH** — RS256 is the industry standard. The existing `JWTValidator` in `echomind_lib/helpers/auth.py` already supports RS256 via PyJWKClient.

#### Token Claims

```json
{
  "iss": "echomind-api",
  "sub": "user_42",
  "aud": "echomind-mcp-gateway",
  "iat": 1708128000,
  "exp": 1708128300,
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "sandbox-a1b2c3d4e5f6",
  "user_id": 42,
  "org_id": 1,
  "team_ids": [5, 12],
  "permissions": [
    "search:read",
    "skills:execute",
    "connectors:read",
    "connectors:sync",
    "api:web_search"
  ],
  "roles": ["user"],
  "groups": ["echomind-allowed"]
}
```

| Claim | Type | Required | Description |
|-------|------|----------|-------------|
| `iss` | string | Yes | Always `"echomind-api"` |
| `sub` | string | Yes | User identifier (`"user_{id}"`) |
| `aud` | string | Yes | Always `"echomind-mcp-gateway"` |
| `iat` | int | Yes | Issued-at timestamp |
| `exp` | int | Yes | Expiration (iat + 300s = 5 minutes) |
| `jti` | string | Yes | Unique token ID (UUID v4) for revocation |
| `session_id` | string | Yes | Sandbox session ID |
| `user_id` | int | Yes | Database user ID |
| `org_id` | int | Yes | Organization ID |
| `team_ids` | int[] | Yes | User's team IDs (for collection scoping) |
| `permissions` | string[] | Yes | Granted tool permissions |
| `roles` | string[] | Yes | User roles from Authentik |
| `groups` | string[] | Yes | Authentik groups (for PermissionChecker) |

### 3.3 Token Lifetime and Refresh

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **TTL** | 5 minutes | Short enough to limit stolen token damage; long enough for multi-turn conversations |
| **Refresh** | Sandbox requests new JWT from API via NATS | Avoids direct API HTTP call from sandbox |
| **Revocation** | On session release (DESTROYED state) | SandboxManager publishes revocation event |
| **Clock Skew** | 30 seconds | Standard leeway for distributed systems |

**Refresh Flow**:
```
Sandbox                        NATS                          API
  |                              |                             |
  |── sandbox.{sid}.control ────>|                             |
  |   {"type": "token_refresh"}  |── deliver ────────────────>|
  |                              |                             |── Sign new JWT
  |<── sandbox.{sid}.control ───|<── publish ────────────────|
  |   {"type": "token",          |                             |
  |    "jwt": "eyJ..."}          |                             |
```

### 3.4 Key Management

**Signing Key Storage**: RSA 2048-bit key pair stored in a new `jwt_signing_keys` database table. The API reads the active private key to sign sandbox JWTs. The MCP gateway fetches the public key via a JWKS endpoint served by the API.

**Key Rotation**: New keys are generated periodically (every 30 days by default). Both old and new keys are valid during the overlap period (7 days). The MCP gateway's `PyJWKClient` automatically fetches updated keys from the JWKS endpoint.

**JWKS Endpoint**: `GET /api/v1/.well-known/jwks.json` — served by the API, returns all active public keys in JWKS format.

[RFC 7517 — JSON Web Key (JWK) — https://datatracker.ietf.org/doc/html/rfc7517]

**Confidence: HIGH** — PyJWT's `PyJWKClient` handles JWKS fetching and caching automatically.

---

## 4. MCP Gateway Auth Middleware

### 4.1 Architecture

Auth middleware is inserted into the FastMCP middleware stack **before** the audit logger and error handler. Every tool call passes through auth validation before reaching the tool handler.

```
MCP Tool Call
     │
     ▼
┌─────────────────────┐
│ AuthMiddleware       │ ← NEW (Phase 8)
│  - Extract JWT       │
│  - Validate signature│
│  - Check expiry      │
│  - Extract claims    │
│  - Store in context  │
└──────────┬──────────┘
           │
     ▼
┌─────────────────────┐
│ RBACMiddleware       │ ← NEW (Phase 8)
│  - Check permissions │
│  - Scope request     │
└──────────┬──────────┘
           │
     ▼
┌─────────────────────┐
│ RateLimitMiddleware  │ ← NEW (Phase 8)
│  - Check rate limits │
│  - Update counters   │
└──────────┬──────────┘
           │
     ▼
┌─────────────────────┐
│ ErrorHandlingMiddle  │ (existing)
└──────────┬──────────┘
           │
     ▼
┌─────────────────────┐
│ AuditLoggingMiddle   │ (existing, enhanced)
└──────────┬──────────┘
           │
     ▼
  Tool Handler
```

### 4.2 Auth Middleware Implementation

```python
"""
JWT authentication middleware for MCP Gateway.

Validates JWT tokens on every tool call, extracts user claims,
and stores them in the FastMCP context for downstream middleware
and tool handlers.

References:
    - RFC 9068: JWT Profile for OAuth 2.0 Access Tokens
    - OWASP API Security Top 10 2023: API2 Broken Authentication
"""

import logging
from datetime import datetime, timezone

from fastmcp.server.middleware import Middleware, MiddlewareContext
from jwt import PyJWKClient

from echomind_lib.helpers.auth import JWTValidator, TokenUser

logger = logging.getLogger("echomind-mcp-gateway")


class AuthMiddleware(Middleware):
    """
    JWT authentication middleware for FastMCP.

    Extracts Bearer token from MCP request metadata, validates it
    using the configured JWTValidator, and stores the TokenUser
    in the middleware context for downstream use.

    Attributes:
        _validator: JWTValidator configured with JWKS endpoint.
        _revoked_tokens: Set of revoked JTI values (short-lived cache).
    """

    def __init__(
        self,
        jwks_url: str,
        issuer: str = "echomind-api",
        audience: str = "echomind-mcp-gateway",
    ) -> None:
        """
        Initialize auth middleware.

        Args:
            jwks_url: URL to the API's JWKS endpoint.
            issuer: Expected token issuer.
            audience: Expected token audience.
        """
        self._validator = JWTValidator(
            issuer=issuer,
            audience=audience,
            jwks_url=jwks_url,
        )
        self._revoked_tokens: set[str] = set()

    def revoke_token(self, jti: str) -> None:
        """
        Add a token ID to the revocation set.

        Args:
            jti: JWT ID to revoke.
        """
        self._revoked_tokens.add(jti)
        # Prune expired entries periodically (simple size-based limit)
        if len(self._revoked_tokens) > 10_000:
            self._revoked_tokens.clear()

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: object,
    ) -> object:
        """
        Validate JWT before tool execution.

        Args:
            context: Middleware context with request details.
            call_next: Next handler in middleware chain.

        Returns:
            Tool execution result.

        Raises:
            ToolError: If authentication fails.
        """
        from fastmcp.exceptions import ToolError

        # Extract token from request metadata
        # FastMCP passes session metadata including HTTP headers
        token = self._extract_token(context)
        if not token:
            raise ToolError("Authentication required: missing Bearer token")

        # Validate JWT
        try:
            user = self._validator.validate_token(token)
        except Exception as e:
            logger.warning(f"🔒 JWT validation failed: {e}")
            raise ToolError("Authentication failed: invalid or expired token") from e

        # Check revocation
        payload = self._validator.decode_without_validation(token)
        jti = payload.get("jti")
        if jti and jti in self._revoked_tokens:
            raise ToolError("Authentication failed: token has been revoked")

        # Store user and claims in context for downstream middleware
        context.extra["user"] = user
        context.extra["session_id"] = payload.get("session_id")
        context.extra["user_id"] = payload.get("user_id")
        context.extra["org_id"] = payload.get("org_id")
        context.extra["team_ids"] = payload.get("team_ids", [])
        context.extra["permissions"] = payload.get("permissions", [])

        return await call_next(context)

    @staticmethod
    def _extract_token(context: MiddlewareContext) -> str | None:
        """
        Extract Bearer token from MCP session metadata.

        FastMCP's HTTP transport passes HTTP headers in session metadata.
        The sandbox client sends the JWT as a Bearer token in the
        Authorization header.

        Args:
            context: Middleware context.

        Returns:
            Token string or None.
        """
        # FastMCP stores HTTP headers in session state
        headers = getattr(context, "headers", {}) or {}
        auth_header = headers.get("authorization", "")
        if not auth_header:
            # Try session metadata (transport-dependent)
            metadata = getattr(context, "metadata", {}) or {}
            auth_header = metadata.get("authorization", "")

        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return parts[1]
```

**Dependencies**: `PyJWT[crypto]>=2.8.0`, `cryptography>=42.0.0`, existing `echomind_lib.helpers.auth`

**Confidence: MEDIUM** — The exact mechanism for extracting HTTP headers from FastMCP's `MiddlewareContext` depends on FastMCP version. The `context.headers` or session metadata approach needs validation against FastMCP 2.14/3.0 internals.

### 4.3 RBAC Middleware Implementation

```python
"""
RBAC enforcement middleware for MCP Gateway.

Checks tool-level permissions from JWT claims before allowing
execution. Delegates to PermissionChecker for data-scoping decisions.

References:
    - OWASP API Security Top 10 2023: API1 Broken Object Level Authorization
    - OWASP API Security Top 10 2023: API5 Broken Function Level Authorization
"""

import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger("echomind-mcp-gateway")

# Tool -> Required permission mapping
TOOL_PERMISSIONS: dict[str, str] = {
    # Search namespace
    "search_documents": "search:read",
    "search_collections": "search:read",
    "get_document": "search:read",
    "get_document_chunks": "search:read",
    # Skills namespace
    "skills_list": "skills:execute",
    "skills_get_info": "skills:execute",
    "skills_execute": "skills:execute",
    # Connectors namespace
    "connectors_list": "connectors:read",
    "connector_status": "connectors:read",
    "connector_search": "connectors:read",
    "connector_sync": "connectors:sync",
    # API proxy namespace
    "web_search": "api:web_search",
    "send_email": "api:email",
    "calendar_create_event": "api:calendar",
    "calendar_list_events": "api:calendar",
}


class RBACMiddleware(Middleware):
    """
    Role-Based Access Control middleware.

    Checks that the authenticated user (from AuthMiddleware) has
    the required permission for the requested tool.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: object,
    ) -> object:
        """
        Check permissions before tool execution.

        Args:
            context: Middleware context (must contain 'user' and 'permissions').
            call_next: Next handler in chain.

        Returns:
            Tool execution result.

        Raises:
            ToolError: If permission is denied.
        """
        from fastmcp.exceptions import ToolError

        tool_name = context.message.name
        required_permission = TOOL_PERMISSIONS.get(tool_name)

        if required_permission is None:
            # Unknown tool — deny by default (fail-closed)
            logger.warning(f"🔒 Unknown tool '{tool_name}' — no permission mapping")
            raise ToolError(f"Access denied: unknown tool '{tool_name}'")

        user_permissions = context.extra.get("permissions", [])
        if required_permission not in user_permissions:
            user_id = context.extra.get("user_id", "unknown")
            logger.warning(
                f"🔒 Permission denied: user={user_id}, "
                f"tool={tool_name}, required={required_permission}"
            )
            raise ToolError(
                f"Permission denied: '{required_permission}' required for '{tool_name}'"
            )

        return await call_next(context)
```

### 4.4 Request Scoping

After auth and RBAC checks pass, search tools must scope their results to the user's accessible collections. The existing `PermissionChecker.get_search_collections()` method already implements this logic.

**Integration Point**: The `SearchBackend.search()` method gains a `collections` parameter. The search tool handler reads `context.extra["user_id"]` and `context.extra["team_ids"]` to compute the allowed collection list:

```python
# In search tool handler (modified)
async def search_documents(ctx: Context, query: str, limit: int = 10, ...) -> list[SearchResult]:
    user_id = ctx.extra.get("user_id")
    team_ids = ctx.extra.get("team_ids", [])

    # Compute scoped collections
    collections = [f"user_{user_id}"]
    for tid in team_ids:
        collections.append(f"team_{tid}")
    collections.append("org_default")

    results = await backend.search(query=query, limit=limit, collections=collections)
    return [SearchResult(**r) for r in results]
```

**Confidence: HIGH** — The `get_search_collections()` logic is proven and the search backend already accepts a `collections` parameter.

---

## 5. RBAC Enforcement

### 5.1 Permission Model

Permissions follow the format `{namespace}:{action}`. Each sandbox JWT includes the complete list of granted permissions.

| Permission | Tools | Default Role |
|-----------|-------|-------------|
| `search:read` | search_documents, search_collections, get_document, get_document_chunks | `user` |
| `skills:execute` | skills_list, skills_get_info, skills_execute | `user` |
| `connectors:read` | connectors_list, connector_status, connector_search | `user` |
| `connectors:sync` | connector_sync | `user` |
| `api:web_search` | web_search | `user` |
| `api:email` | send_email | `user` (if connector configured) |
| `api:calendar` | calendar_create_event, calendar_list_events | `user` (if connector configured) |

### 5.2 Per-Connector Access Control

Connector tools enforce the same RBAC as the API:

| Scope | Who Can View | Who Can Sync |
|-------|-------------|-------------|
| `user` | Owner only | Owner only |
| `team` | Team members | Team leads + admins |
| `org` | All allowed users | Admins only |

The connector backend receives the `TokenUser` from the middleware context and uses `PermissionChecker` to filter results:

```python
# In connector tool handler
async def connectors_list(ctx: Context) -> list[ConnectorInfo]:
    user = ctx.extra["user"]
    db = await get_db_session()
    checker = PermissionChecker(db)
    connector_ids = await checker.get_accessible_connector_ids(user)
    # Query only accessible connectors
    ...
```

### 5.3 Admin Override

Users with the `echomind-admins` group in their JWT claims bypass all permission checks. The `PermissionChecker.is_admin()` method already handles this:

```python
if checker.is_admin(user):
    # Admin: return all connectors, search all collections
```

**Confidence: HIGH** — `PermissionChecker` is battle-tested in the API service.

---

## 6. Rate Limiting

### 6.1 Algorithm: Sliding Window Counter

**Choice**: Sliding window counter over fixed window or token bucket.

**Rationale**:
- **vs Fixed Window**: Sliding window prevents the boundary burst problem where a client sends 2x the limit by straddling two windows.
- **vs Token Bucket**: Simpler implementation, predictable behavior, no burst allowance needed for MCP tools.
- **Memory**: O(1) per client (two counters per window).

[Redis Rate Limiting Tutorial — https://redis.io/tutorials/howtos/ratelimiting/]

### 6.2 Rate Limits

| Scope | Limit | Window | Rationale |
|-------|-------|--------|-----------|
| **Per-user** | 100 tool calls | 1 minute | Prevents resource exhaustion across sessions |
| **Per-session** | 30 tool calls | 1 minute | Prevents a single session from monopolizing |
| **Per-tool (search)** | 20 calls | 1 minute | Search is expensive (embedding + Qdrant) |
| **Per-tool (skills_execute)** | 10 calls | 1 minute | Subprocess execution is heavyweight |
| **Per-tool (connector_sync)** | 2 calls | 5 minutes | Sync triggers full pipeline |

### 6.3 Implementation

```python
"""
Rate limiting middleware for MCP Gateway.

Implements sliding window counter algorithm with configurable
per-user, per-session, and per-tool limits.

References:
    - OWASP API Security Top 10 2023: API4 Unrestricted Resource Consumption
    - Redis rate limiting: https://redis.io/tutorials/howtos/ratelimiting/
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger("echomind-mcp-gateway")


@dataclass
class WindowCounter:
    """Sliding window counter state."""

    prev_count: int = 0
    curr_count: int = 0
    window_start: float = 0.0


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a scope."""

    max_requests: int
    window_seconds: int


# Default rate limits
DEFAULT_LIMITS: dict[str, RateLimitConfig] = {
    "user": RateLimitConfig(max_requests=100, window_seconds=60),
    "session": RateLimitConfig(max_requests=30, window_seconds=60),
}

TOOL_LIMITS: dict[str, RateLimitConfig] = {
    "search_documents": RateLimitConfig(max_requests=20, window_seconds=60),
    "skills_execute": RateLimitConfig(max_requests=10, window_seconds=60),
    "connector_sync": RateLimitConfig(max_requests=2, window_seconds=300),
}


class RateLimitMiddleware(Middleware):
    """
    Sliding window counter rate limiter.

    Tracks request counts per user, per session, and per tool.
    Returns Retry-After header via ToolError when limit is exceeded.
    """

    def __init__(self) -> None:
        """Initialize rate limiter with empty counters."""
        self._counters: dict[str, WindowCounter] = defaultdict(WindowCounter)

    def _check_limit(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> tuple[bool, int, int]:
        """
        Check if a request is within the rate limit.

        Args:
            key: Rate limit key (e.g., "user:42", "session:abc").
            config: Rate limit configuration.

        Returns:
            Tuple of (allowed, remaining, retry_after_seconds).
        """
        now = time.monotonic()
        counter = self._counters[key]

        window_start = now - (now % config.window_seconds)

        if counter.window_start < window_start - config.window_seconds:
            # Both windows expired, reset
            counter.prev_count = 0
            counter.curr_count = 0
            counter.window_start = window_start
        elif counter.window_start < window_start:
            # Current window rolled over
            counter.prev_count = counter.curr_count
            counter.curr_count = 0
            counter.window_start = window_start

        # Weighted count
        elapsed = (now - counter.window_start) / config.window_seconds
        weighted = counter.prev_count * (1 - elapsed) + counter.curr_count

        if weighted >= config.max_requests:
            retry_after = int(config.window_seconds - (now - counter.window_start))
            return False, 0, max(1, retry_after)

        counter.curr_count += 1
        remaining = max(0, int(config.max_requests - weighted - 1))
        return True, remaining, 0

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: object,
    ) -> object:
        """
        Check rate limits before tool execution.

        Args:
            context: Middleware context.
            call_next: Next handler.

        Returns:
            Tool execution result.

        Raises:
            ToolError: If rate limit exceeded.
        """
        user_id = context.extra.get("user_id", "unknown")
        session_id = context.extra.get("session_id", "unknown")
        tool_name = context.message.name

        # Check per-user limit
        allowed, remaining, retry_after = self._check_limit(
            f"user:{user_id}", DEFAULT_LIMITS["user"]
        )
        if not allowed:
            logger.warning(f"🚫 Rate limit exceeded: user={user_id}")
            raise ToolError(
                f"Rate limit exceeded. Retry after {retry_after}s. "
                f"(limit: {DEFAULT_LIMITS['user'].max_requests}/min per user)"
            )

        # Check per-session limit
        allowed, remaining, retry_after = self._check_limit(
            f"session:{session_id}", DEFAULT_LIMITS["session"]
        )
        if not allowed:
            logger.warning(f"🚫 Rate limit exceeded: session={session_id}")
            raise ToolError(
                f"Rate limit exceeded. Retry after {retry_after}s. "
                f"(limit: {DEFAULT_LIMITS['session'].max_requests}/min per session)"
            )

        # Check per-tool limit (if configured)
        tool_config = TOOL_LIMITS.get(tool_name)
        if tool_config:
            allowed, remaining, retry_after = self._check_limit(
                f"tool:{user_id}:{tool_name}", tool_config
            )
            if not allowed:
                logger.warning(
                    f"🚫 Rate limit exceeded: user={user_id}, tool={tool_name}"
                )
                raise ToolError(
                    f"Rate limit exceeded for '{tool_name}'. "
                    f"Retry after {retry_after}s."
                )

        return await call_next(context)
```

### 6.4 Storage Backend

**Phase 8**: In-memory (process-local). Sufficient for single-instance MCP gateway.

**Future**: Redis backend for multi-instance scaling. The `_counters` dict is replaced with Redis INCR + EXPIRE operations. The algorithm remains identical.

**Confidence: HIGH** — Sliding window counter is well-documented and the implementation is straightforward.

---

## 7. Network Security

### 7.1 Docker Network Topology (Hardened)

```
+=====================================================================+
|                        FRONTEND network                              |
|   traefik, api, webui, minio, authentik-server                      |
+=================================+===================================+
                                  |
                             Traefik routing
                                  |
+=================================+===================================+
|                        BACKEND network                               |
|   postgres, qdrant, minio, nats, redis, api, embedder, orchestrator,|
|   connector, ingestor, guardian, projector, mcp-gateway              |
+=================================+===================================+
                                  |
                    mcp-gateway bridge
                                  |
+=================================+===================================+
|                        SANDBOX network                               |
|   mcp-gateway, sandbox-0, sandbox-1, ...                            |
|                                                                      |
|   iptables DOCKER-USER rules:                                        |
|   ✅ sandbox → mcp-gateway:8100 (MCP tools)                         |
|   ✅ sandbox → nats:4222 (via backend bridge)                        |
|   ✅ sandbox → internet (web search, web crawl)                      |
|   ❌ sandbox → postgres:5432 (BLOCKED)                               |
|   ❌ sandbox → qdrant:6333/6334 (BLOCKED)                            |
|   ❌ sandbox → minio:9000 (BLOCKED)                                  |
|   ❌ sandbox → redis:6379 (BLOCKED)                                  |
|   ❌ sandbox → embedder:50051 (BLOCKED)                              |
+=====================================================================+
```

### 7.2 iptables Rules

Applied via a startup script on the Docker host. Uses the `DOCKER-USER` chain which Docker processes before its own rules.

[Docker iptables documentation — https://docs.docker.com/engine/network/firewall-iptables/]

```bash
#!/bin/bash
# deployment/scripts/sandbox-firewall.sh
# Apply iptables rules to restrict sandbox container network access.
# Must be run on the Docker host as root.

set -euo pipefail

# Resolve container IPs by service name
# These are stable within a compose project
SANDBOX_SUBNET="172.30.0.0/16"  # Sandbox network subnet
POSTGRES_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' data-postgres 2>/dev/null || echo "")
QDRANT_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' data-qdrant 2>/dev/null || echo "")
MINIO_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' data-minio 2>/dev/null || echo "")
REDIS_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' data-redis 2>/dev/null || echo "")
EMBEDDER_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' echomind-embedder 2>/dev/null || echo "")

# Flush existing sandbox rules (idempotent)
iptables -D DOCKER-USER -s "$SANDBOX_SUBNET" -d "$POSTGRES_IP" -j DROP 2>/dev/null || true
iptables -D DOCKER-USER -s "$SANDBOX_SUBNET" -d "$QDRANT_IP" -j DROP 2>/dev/null || true
iptables -D DOCKER-USER -s "$SANDBOX_SUBNET" -d "$MINIO_IP" -j DROP 2>/dev/null || true
iptables -D DOCKER-USER -s "$SANDBOX_SUBNET" -d "$REDIS_IP" -j DROP 2>/dev/null || true
iptables -D DOCKER-USER -s "$SANDBOX_SUBNET" -d "$EMBEDDER_IP" -j DROP 2>/dev/null || true

# Block sandbox -> backend data services
[ -n "$POSTGRES_IP" ] && iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -d "$POSTGRES_IP" -j DROP
[ -n "$QDRANT_IP" ] && iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -d "$QDRANT_IP" -j DROP
[ -n "$MINIO_IP" ] && iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -d "$MINIO_IP" -j DROP
[ -n "$REDIS_IP" ] && iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -d "$REDIS_IP" -j DROP
[ -n "$EMBEDDER_IP" ] && iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -d "$EMBEDDER_IP" -j DROP

echo "✅ Sandbox firewall rules applied"
iptables -L DOCKER-USER -n --line-numbers
```

**Integration**: Add to `cluster.sh` as a post-start hook when `ENABLE_SANDBOX=true`.

### 7.3 MCP Gateway: Internal Only

The MCP gateway must NEVER be exposed to the internet. It is accessible only from the `backend` and `sandbox` Docker networks.

```yaml
# docker-compose-sandbox.yml (already correct)
mcp-gateway:
  labels:
    - "traefik.enable=false"  # No Traefik routing
  networks:
    - backend   # Reaches Qdrant, PG, Embedder
    - sandbox   # Reachable from sandboxes
```

**Confidence: HIGH** — The network topology is already implemented in Phase 4. Phase 8 adds iptables hardening.

---

## 8. Secret Management

### 8.1 JWT Signing Key Storage

| Secret | Storage | Rotation | Access |
|--------|---------|----------|--------|
| RSA private key (signing) | `jwt_signing_keys` table (encrypted) | 30 days | API service only |
| RSA public key (verification) | JWKS endpoint | Same as private key | MCP gateway (read-only) |
| Authentik OIDC client secret | `.env` file | Manual | API service |
| API keys (Google, OpenAI, etc.) | `.env` file → `ApiKeyManager` | Manual | MCP gateway (never exposed to agents) |

### 8.2 API Key Encryption at Rest

API keys loaded by `ApiKeyManager` are stored as `SecretStr` (Pydantic) which prevents accidental logging. For database-stored keys (future connector OAuth tokens), AES-256-GCM encryption is used with a master key from the environment.

### 8.3 Environment Variable Security

- Sandbox containers receive ONLY: `SANDBOX_SESSION_ID`, `SANDBOX_USER_ID`, `SANDBOX_NATS_URL`, `SANDBOX_MCP_URL`, and the session JWT.
- The `DockerSandboxBackend` already drops all capabilities and uses a clean environment.
- The `SkillExecutor` already filters environment variables to a safe subset (`PATH`, `HOME`, `USER`, `LANG`, etc.).

**Confidence: HIGH** — Existing implementations already handle this. Phase 8 adds the JWT signing key table.

---

## 9. Audit Trail

### 9.1 Security Event Types

| Event Type | Trigger | Severity | Stored In |
|-----------|---------|----------|-----------|
| `auth.success` | JWT validated successfully | INFO | NATS audit stream |
| `auth.failure` | Invalid/expired/revoked JWT | WARN | DB `security_audit_log` + NATS |
| `auth.token_issued` | API signs new sandbox JWT | INFO | DB `security_audit_log` |
| `auth.token_revoked` | Session ended, token revoked | INFO | DB `security_audit_log` |
| `rbac.denied` | Permission check failed | WARN | DB `security_audit_log` + NATS |
| `rbac.admin_override` | Admin bypassed permission check | INFO | DB `security_audit_log` |
| `rate_limit.exceeded` | Rate limit hit | WARN | DB `security_audit_log` + NATS |
| `network.blocked` | iptables dropped sandbox packet | WARN | Docker host syslog |

### 9.2 Database Table: `security_audit_log`

```sql
CREATE TABLE IF NOT EXISTS security_audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    user_id INTEGER,
    session_id VARCHAR(255),
    tool_name VARCHAR(100),
    detail JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_audit_event_type
ON security_audit_log(event_type);

CREATE INDEX IF NOT EXISTS idx_security_audit_user_id
ON security_audit_log(user_id);

CREATE INDEX IF NOT EXISTS idx_security_audit_created_at
ON security_audit_log(created_at);
```

### 9.3 Enhanced Audit Logger

The existing `AuditLoggingMiddleware` is enhanced to include user identity and security events:

```python
# Enhanced audit log entry (Phase 8)
{
    "timestamp": "2026-02-17T14:30:00.123Z",
    "event": "mcp_tool_call",
    "tool": "search_documents",
    "user_id": 42,
    "session_id": "sandbox-a1b2c3d4e5f6",
    "parameters": {"query": "quarterly report", "limit": 10},
    "result_status": "success",
    "duration_ms": 234,
    "error": null,
    "permissions_used": ["search:read"],
    "collections_searched": ["user_42", "team_5", "org_default"]
}
```

---

## 10. Database Schema Changes

### 10.1 Alembic Migration

File: `src/migration/migrations/versions/YYYYMMDD_HHMMSS_add_auth_security_tables.py`

```python
"""Add auth and security hardening tables.

Creates:
- jwt_signing_keys: RSA key pairs for sandbox JWT signing
- security_audit_log: Security event audit trail

Revision ID: YYYYMMDD_HHMMSS
"""

import sqlalchemy as sa
from alembic import op

revision = "YYYYMMDD_HHMMSS"
down_revision = "20260216_010000"  # After sandbox tables
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add auth and security tables."""
    # JWT signing keys
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jwt_signing_keys (
            id SERIAL PRIMARY KEY,
            key_id VARCHAR(64) UNIQUE NOT NULL,
            algorithm VARCHAR(10) NOT NULL DEFAULT 'RS256',
            private_key_pem TEXT NOT NULL,
            public_key_pem TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            rotated_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jwt_signing_keys_active
        ON jwt_signing_keys(is_active) WHERE is_active = true
        """
    )

    # Security audit log
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS security_audit_log (
            id BIGSERIAL PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            user_id INTEGER,
            session_id VARCHAR(255),
            tool_name VARCHAR(100),
            detail JSONB DEFAULT '{}',
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_security_audit_event_type
        ON security_audit_log(event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_security_audit_user_id
        ON security_audit_log(user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_security_audit_created_at
        ON security_audit_log(created_at)
        """
    )


def downgrade() -> None:
    """Remove auth and security tables."""
    op.execute("DROP TABLE IF EXISTS security_audit_log")
    op.execute("DROP TABLE IF EXISTS jwt_signing_keys")
```

---

## 11. Proto Definitions

### 11.1 Auth Proto Messages

File: `src/proto/internal/auth.proto`

```protobuf
syntax = "proto3";
package echomind.internal;
option go_package = "echomind/proto/internal";

import "google/protobuf/timestamp.proto";

// JWT token request from API to sign for sandbox session
message SandboxTokenRequest {
    int32 user_id = 1;
    string session_id = 2;
    int32 org_id = 3;
    repeated int32 team_ids = 4;
    repeated string permissions = 5;
    repeated string roles = 6;
    repeated string groups = 7;
    int32 ttl_seconds = 8;  // Default: 300 (5 minutes)
}

// Signed JWT response
message SandboxTokenResponse {
    string token = 1;
    google.protobuf.Timestamp expires_at = 2;
    string jti = 3;  // Token ID for revocation
}

// Token refresh request (sandbox -> API via NATS)
message TokenRefreshRequest {
    string session_id = 1;
    string current_jti = 2;  // Current token ID
}

// Security audit event
message SecurityAuditEvent {
    string event_type = 1;
    int32 user_id = 2;
    string session_id = 3;
    string tool_name = 4;
    string detail_json = 5;
    string ip_address = 6;
    google.protobuf.Timestamp created_at = 7;
}
```

After creating this file, run: `./scripts/generate_proto.sh`

---

## 12. Files to Create/Modify

### New Files

| # | File | Purpose |
|---|------|---------|
| 1 | `src/mcp_gateway/middleware/auth.py` | JWT authentication middleware |
| 2 | `src/mcp_gateway/middleware/rbac.py` | RBAC enforcement middleware |
| 3 | `src/mcp_gateway/middleware/rate_limiter.py` | Sliding window rate limiter |
| 4 | `src/mcp_gateway/auth/__init__.py` | Auth package |
| 5 | `src/mcp_gateway/auth/jwt_signer.py` | JWT signing for sandbox tokens (used by API) |
| 6 | `src/mcp_gateway/auth/permissions.py` | Tool permission mappings |
| 7 | `src/api/routes/jwks.py` | JWKS endpoint (`/.well-known/jwks.json`) |
| 8 | `src/api/logic/sandbox_token_service.py` | Service to sign sandbox JWTs |
| 9 | `src/proto/internal/auth.proto` | Auth proto messages |
| 10 | `src/migration/migrations/versions/YYYYMMDD_HHMMSS_add_auth_security_tables.py` | DB migration |
| 11 | `deployment/scripts/sandbox-firewall.sh` | iptables rules for sandbox network |
| 12 | `tests/unit/mcp_gateway/test_auth_middleware.py` | Auth middleware tests |
| 13 | `tests/unit/mcp_gateway/test_rbac_middleware.py` | RBAC middleware tests |
| 14 | `tests/unit/mcp_gateway/test_rate_limiter.py` | Rate limiter tests |
| 15 | `tests/unit/api/test_jwks_endpoint.py` | JWKS endpoint tests |
| 16 | `tests/unit/api/test_sandbox_token_service.py` | Token signing tests |

### Modified Files

| # | File | Changes |
|---|------|---------|
| 1 | `src/mcp_gateway/main.py` | Add AuthMiddleware, RBACMiddleware, RateLimitMiddleware to stack |
| 2 | `src/mcp_gateway/config.py` | Add `jwks_url`, `auth_enabled` settings |
| 3 | `src/mcp_gateway/middleware/audit_logger.py` | Add user_id, session_id to audit entries |
| 4 | `src/mcp_gateway/tools/search.py` | Scope search by user's collections from JWT claims |
| 5 | `src/mcp_gateway/tools/connectors.py` | Filter connectors by user permissions |
| 6 | `src/api/sandbox/manager.py` | Sign JWT and inject into sandbox env on assign |
| 7 | `src/api/main.py` | Add JWKS route, initialize key rotation |
| 8 | `src/mcp_gateway/requirements.txt` | Add `PyJWT[crypto]>=2.8.0`, `cryptography>=42.0.0` |
| 9 | `deployment/docker-cluster/docker-compose-sandbox.yml` | Add JWT-related env vars to MCP gateway |
| 10 | `deployment/docker-cluster/.env.example` | Add `SANDBOX_JWT_*` variables |
| 11 | `deployment/docker-cluster/cluster.sh` | Add sandbox-firewall.sh post-start hook |

---

## 13. Dependencies

| Package | Version | Service | Purpose |
|---------|---------|---------|---------|
| `PyJWT[crypto]` | `>=2.8.0,<3.0` | MCP Gateway, API | JWT signing/verification with RS256 |
| `cryptography` | `>=42.0.0,<44.0` | MCP Gateway, API | RSA key generation, JWKS |

Both packages are already indirect dependencies via `PyJWT` (used in `echomind_lib/helpers/auth.py`). Phase 8 makes them explicit with version pins.

[PyJWT documentation — https://pyjwt.readthedocs.io/en/stable/]
[PyJWT JWKS support — https://pyjwt.readthedocs.io/en/stable/usage.html]

---

## 14. Unit Test Plan

### `tests/unit/mcp_gateway/test_auth_middleware.py` (~15 tests)

| Test | Description |
|------|-------------|
| `test_valid_jwt_passes` | Valid JWT with all claims allows tool execution |
| `test_missing_token_rejects` | No Authorization header returns ToolError |
| `test_malformed_token_rejects` | Invalid JWT string returns ToolError |
| `test_expired_token_rejects` | Token past exp returns ToolError |
| `test_wrong_issuer_rejects` | Token with wrong iss returns ToolError |
| `test_wrong_audience_rejects` | Token with wrong aud returns ToolError |
| `test_missing_required_claims` | Token without session_id/user_id rejects |
| `test_revoked_token_rejects` | Token in revocation set rejects |
| `test_user_stored_in_context` | TokenUser stored in context.extra["user"] |
| `test_permissions_extracted` | Permissions list stored in context.extra |
| `test_team_ids_extracted` | team_ids stored in context.extra |
| `test_clock_skew_tolerance` | Token expired <30s ago still accepted |
| `test_future_iat_rejects` | Token with future iat rejects |
| `test_bearer_prefix_required` | "Token xyz" (not "Bearer xyz") rejects |
| `test_empty_bearer_rejects` | "Bearer " with no token rejects |

### `tests/unit/mcp_gateway/test_rbac_middleware.py` (~10 tests)

| Test | Description |
|------|-------------|
| `test_allowed_permission_passes` | User with search:read can call search_documents |
| `test_missing_permission_rejects` | User without skills:execute cannot call skills_execute |
| `test_unknown_tool_rejects` | Unregistered tool name returns ToolError |
| `test_admin_has_all_permissions` | Admin user can call any tool |
| `test_empty_permissions_rejects_all` | User with no permissions blocked |
| `test_connector_sync_requires_sync_perm` | connector_sync needs connectors:sync |
| `test_search_scoped_to_user_collections` | search_documents only searches user's collections |
| `test_connector_list_filtered_by_rbac` | connectors_list returns only accessible connectors |
| `test_permission_check_reads_from_context` | Permissions come from context.extra, not re-validated |
| `test_fail_closed_default` | Missing permission mapping defaults to deny |

### `tests/unit/mcp_gateway/test_rate_limiter.py` (~12 tests)

| Test | Description |
|------|-------------|
| `test_under_limit_passes` | 29 calls in 1min pass for 30/min limit |
| `test_at_limit_rejects` | 31st call in 1min returns ToolError |
| `test_window_rolls_over` | After 1min, counter resets |
| `test_sliding_window_smooth` | Boundary burst limited (not 2x fixed window) |
| `test_per_user_limit` | 100 calls/min per user across sessions |
| `test_per_session_limit` | 30 calls/min per session |
| `test_per_tool_search_limit` | 20 search_documents calls/min |
| `test_per_tool_skills_limit` | 10 skills_execute calls/min |
| `test_per_tool_sync_limit` | 2 connector_sync calls/5min |
| `test_different_users_independent` | User A's count doesn't affect User B |
| `test_retry_after_in_error` | ToolError includes retry-after seconds |
| `test_rate_limit_resets_after_window` | Counter fully resets after 2x window |

### `tests/unit/api/test_jwks_endpoint.py` (~5 tests)

| Test | Description |
|------|-------------|
| `test_jwks_returns_public_keys` | Endpoint returns valid JWKS JSON |
| `test_jwks_format_correct` | Response contains kty, kid, n, e fields |
| `test_inactive_keys_excluded` | Rotated-out keys not in response |
| `test_multiple_keys_during_rotation` | Both old and new keys present during overlap |
| `test_cache_headers_set` | Response includes Cache-Control headers |

### `tests/unit/api/test_sandbox_token_service.py` (~8 tests)

| Test | Description |
|------|-------------|
| `test_sign_token_valid` | Signed token is verifiable with public key |
| `test_claims_complete` | All required claims present in token |
| `test_expiry_5_minutes` | exp = iat + 300 |
| `test_jti_unique` | Each token has unique jti |
| `test_audience_set` | aud = "echomind-mcp-gateway" |
| `test_issuer_set` | iss = "echomind-api" |
| `test_permissions_from_user` | Permissions derived from user roles/groups |
| `test_team_ids_included` | User's team IDs included in claims |

### Security-Specific Tests (~10 tests)

| Test | Description |
|------|-------------|
| `test_token_forgery_rejected` | Token signed with wrong key rejected |
| `test_algorithm_confusion_blocked` | HS256 token rejected when RS256 expected |
| `test_none_algorithm_blocked` | alg=none token rejected |
| `test_privilege_escalation_blocked` | Modifying permissions in token fails validation |
| `test_cross_session_token_blocked` | Token for session A rejected by session B scope |
| `test_expired_token_replay_blocked` | Replaying expired token rejected |
| `test_revoked_token_blocked` | Using revoked jti rejected |
| `test_sql_injection_in_claims_safe` | Malicious strings in claims don't break DB queries |
| `test_unicode_in_claims_handled` | Unicode in user_name doesn't crash |
| `test_oversized_token_rejected` | Token >8KB rejected |

### Total: ~60 tests

---

## 15. Implementation Order

| Step | Task | Depends On | Effort |
|------|------|-----------|--------|
| 1 | Proto definition (`auth.proto`) + generate | — | 1h |
| 2 | DB migration (jwt_signing_keys, security_audit_log) | — | 2h |
| 3 | JWT signing service (`api/logic/sandbox_token_service.py`) | Step 2 | 4h |
| 4 | JWKS endpoint (`api/routes/jwks.py`) | Step 3 | 2h |
| 5 | Auth middleware (`mcp_gateway/middleware/auth.py`) | Step 4 | 4h |
| 6 | RBAC middleware (`mcp_gateway/middleware/rbac.py`) | Step 5 | 3h |
| 7 | Rate limit middleware (`mcp_gateway/middleware/rate_limiter.py`) | — | 3h |
| 8 | Wire middleware into `main.py` | Steps 5-7 | 2h |
| 9 | Scope search tools by user collections | Step 6 | 2h |
| 10 | Filter connector tools by RBAC | Step 6 | 2h |
| 11 | Inject JWT in SandboxManager.assign() | Step 3 | 2h |
| 12 | Token refresh via NATS | Step 11 | 3h |
| 13 | Enhanced audit logger (user_id, security events) | Step 5 | 2h |
| 14 | iptables firewall script | — | 2h |
| 15 | Unit tests (all ~60) | Steps 5-14 | 8h |
| 16 | Integration testing | All | 4h |
| **Total** | | | **~44h** |

---

## 16. Evaluation Scorecard

| Criterion | Score (1-10) | Notes |
|-----------|:-----------:|-------|
| **OWASP API Security coverage** | 9 | Addresses API1 (BOLA via RBAC), API2 (Broken Auth via JWT), API4 (Resource Consumption via rate limiting), API5 (BFLA via permission mapping). API3/6/7/8/9/10 addressed by existing architecture. |
| **Defense in depth** | 9 | Four layers: network isolation (iptables), authentication (JWT), authorization (RBAC), rate limiting. Each layer is independently enforceable. |
| **Existing code reuse** | 9 | Reuses JWTValidator, TokenUser, PermissionChecker, PyJWKClient — all battle-tested in the API service. No new auth framework needed. |
| **Minimal blast radius** | 8 | All changes are additive. Auth can be disabled via `MCP_GATEWAY_AUTH_ENABLED=false` for development. No existing behavior is broken. |
| **Token design quality** | 8 | RS256 asymmetric signing, 5min TTL, JWKS rotation, revocation support. Follows RFC 9068 profile. Missing: proof-of-possession binding (future). |
| **Testability** | 9 | 60 planned tests cover auth bypass, expired tokens, permission escalation, rate limits, forgery, algorithm confusion. All middleware is independently testable. |
| **Operational simplicity** | 7 | Key rotation is automatic. Rate limits are in-memory (no Redis dependency). iptables rules require host access. JWKS endpoint adds one more thing to monitor. |

**Overall: 8.4/10** — Comprehensive zero-trust security hardening that builds on proven existing infrastructure.

---

## 17. Citations and Sources

- [RFC 7519 — JSON Web Token (JWT) — IETF](https://datatracker.ietf.org/doc/html/rfc7519) — JWT specification, claims design
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens — IETF](https://datatracker.ietf.org/doc/html/rfc9068) — Token lifetime, audience validation, required claims
- [RFC 7517 — JSON Web Key (JWK) — IETF](https://datatracker.ietf.org/doc/html/rfc7517) — JWKS format, key rotation
- [OWASP API Security Top 10 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) — API1-API10 security risks and mitigations
- [MCP Authorization Specification](https://modelcontextprotocol.io/specification/draft/basic/authorization) — OAuth 2.1 based MCP auth, Bearer tokens, scopes
- [PyJWT Documentation](https://pyjwt.readthedocs.io/en/stable/) — RS256 signing, JWKS client, key management
- [Redis Rate Limiting Tutorial](https://redis.io/tutorials/howtos/ratelimiting/) — Sliding window counter algorithm
- [Docker iptables Documentation](https://docs.docker.com/engine/network/firewall-iptables/) — DOCKER-USER chain, container isolation
- [FastMCP Middleware Documentation](https://gofastmcp.com/servers/middleware) — Middleware hooks, MiddlewareContext
- [EchoMind Resilience Rules](/.claude/rules/resilience.md) — Connection retry patterns
