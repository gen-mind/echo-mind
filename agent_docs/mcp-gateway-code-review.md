# MCP Gateway Code Review — FAANG Principal Engineer Level

**Date**: 2026-02-16
**Scope**: All code from Phases 1-3 — 14 source files, 17 test files, 42 SKILL.md files, Dockerfile, Docker Compose, deployment config.
**Reviewers**: 6 parallel agents (core, search, skills, tests, docker/security, SKILL.md files)

---

## CRITICAL Issues (11)

### C1. `shlex.quote()` vs `${command}` passthrough — Skills are broken OR insecure
- **Files**: `src/mcp_gateway/skills/executor.py:91-96`, 39 of 42 SKILL.md files
- **Description**: 39 out of 42 skills use `command: "${command}"` where the entire shell command is the user-supplied arg. The executor applies `shlex.quote()` which wraps the value in single quotes. This means `skills_execute("github", {"command": "pr list"})` runs `gh 'pr list'` — the shell sees `pr list` as a single argument, not two. Either almost all skills are broken (quoting prevents execution), or there's a security gap (if quoting is somehow bypassed).
- **Impact**: Fundamental design flaw — either 39 skills don't work, or they have zero injection protection.
- **Fix**: Introduce a skill type field (`type: passthrough` vs `type: structured`). Passthrough skills skip `shlex.quote()` on the `${command}` arg but require explicit documentation of the trust model. Structured skills (like `weather`) keep quoting. Remove `$var` support entirely (only `${var}`).

### C2. `$var` replacement is greedy — prefix collision bug
- **Files**: `src/mcp_gateway/skills/executor.py:96`
- **Description**: `command.replace(f"${key}", safe_value)` matches substrings without word boundaries. If args are `{a: "X", ab: "Y"}` and command is `$ab`, replacing `$a` first produces `'X'b` instead of `'Y'`. Depends on dict insertion order — fragile and unpredictable.
- **Impact**: Incorrect command interpolation for any skill with overlapping arg name prefixes.
- **Fix**: Remove line 96 entirely (only support `${var}` syntax). Or use `re.sub(rf'\${key}\b', safe_value, command)` with word boundary.

### C3. Stale backend references after reconnection
- **Files**: `src/mcp_gateway/main.py:250-261, 296-375`
- **Description**: When Qdrant/Embedder reconnects in retry tasks, `self._qdrant = QdrantDB(...)` creates a NEW object, but `SearchBackend` and `ConnectorBackend` still hold references to the OLD (broken) objects. Reconnection succeeds at gateway level but tools keep using dead clients.
- **Impact**: The entire resilience pattern is broken for tool execution. Gateway reports ready but all search/connector tools fail after reconnection.
- **Fix**: Use a mutable holder pattern (e.g., `ClientHolder` dataclass with `.client` attribute) so backends always see the current client. Or pass `self` (the gateway) to backends and have them access `gateway._qdrant` dynamically.

### C4. gRPC channel never reconnects after failure
- **Files**: `src/mcp_gateway/backends/embedder_client.py:56-67, 86-103`
- **Description**: After a gRPC `AioRpcError`, the channel stays in `self._channel` (non-None but broken). `_ensure_connected()` checks `if self._channel is not None` and skips reconnection. All future `embed_query` calls fail permanently until gateway restart.
- **Impact**: After a single transient gRPC failure, the embedder client is permanently broken.
- **Fix**: In the `except grpc.aio.AioRpcError` block, set `self._channel = None` and `self._stub = None` to force reconnection on the next call. Or check channel state via `channel.get_state()` in `_ensure_connected`.

### C5. Timeout kills shell but not child processes
- **Files**: `src/mcp_gateway/skills/executor.py:116`
- **Description**: `process.kill()` sends SIGKILL to the shell process only. Child processes spawned by the shell (curl, python, piped commands) continue running as orphans. Well-known Unix process group issue.
- **Impact**: Zombie/orphan processes accumulate over time, causing resource exhaustion.
- **Fix**: Use process groups:
  ```python
  process = await asyncio.create_subprocess_shell(
      command,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
      start_new_session=True,  # Creates new process group
  )
  # On timeout:
  import os, signal
  os.killpg(os.getpgid(process.pid), signal.SIGKILL)
  ```

### C6. Subprocess inherits full gateway environment
- **Files**: `src/mcp_gateway/skills/executor.py:104`
- **Description**: `create_subprocess_shell` with no `env` parameter inherits the gateway's full environment — DB passwords, API keys, NATS credentials, Qdrant API keys. Any skill command can access these via `env` or `printenv`.
- **Impact**: Any skill command (including LLM-generated ones) can read all service credentials. Total credential exposure.
- **Fix**: Pass a restricted `env` dict to `create_subprocess_shell`:
  ```python
  import os
  safe_env = {
      "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
      "HOME": "/tmp",
      "LANG": os.environ.get("LANG", "C.UTF-8"),
  }
  # Add only skill-specific env vars (e.g., API keys declared in SKILL.md)
  process = await asyncio.create_subprocess_shell(
      command, env=safe_env, cwd="/tmp", ...
  )
  ```

### C7. Missing `.dockerignore` — entire `src/` in build context
- **Files**: Missing `src/.dockerignore`
- **Description**: The Dockerfile uses `context: ../../src` (the entire `src/` directory). Without a `.dockerignore`, the Docker build context includes ALL service source code (`api/`, `connector/`, `semantic/`, etc.), `__pycache__/` directories, `.env` files, and potentially secrets.
- **Impact**: Bloated Docker images, potential secret leakage, slower builds.
- **Fix**: Create `src/.dockerignore`:
  ```
  **/__pycache__
  **/*.pyc
  **/.env*
  **/sample/
  **/test*
  api/
  connector/
  semantic/
  embedder/
  voice/
  vision/
  guardian/
  migration/
  orchestrator/
  search/
  ingestor/
  proto/
  web/
  ```

### C8. `EmbedderClient` has zero test coverage
- **Files**: Missing `tests/unit/mcp_gateway/test_embedder_client.py`
- **Description**: The gRPC client with connection management, error translation (`AioRpcError` → `ConnectionError`), health check, and lazy initialization is completely untested. This is the only source file in the entire MCP Gateway without a corresponding test file.
- **Impact**: Bugs in embedding, connection handling, or error translation would go undetected.
- **Fix**: Create `test_embedder_client.py` covering:
  - `embed_query()` happy path
  - `embed_query()` with empty embeddings response
  - `embed_query()` with gRPC error → `ConnectionError` translation
  - `_ensure_connected()` lazy initialization
  - `close()` when connected and when not connected
  - `health_check()` success and failure paths

### C9. Embedder `health_check()` gives false positives
- **Files**: `src/mcp_gateway/backends/embedder_client.py:113-124`
- **Description**: `health_check()` only creates a channel (which always succeeds for `grpc.aio.insecure_channel` — it's lazy, no actual connection is made). It doesn't make any RPC call to verify the Embedder service is responding.
- **Impact**: `health_check()` returns `True` even when the Embedder service is completely down, giving false positives during startup readiness checks.
- **Fix**: Make an actual lightweight gRPC call (e.g., embed a test string `["health"]`), or use the gRPC health checking protocol (`grpc.health.v1`).

### C10. Retry tasks not awaited during shutdown
- **Files**: `src/mcp_gateway/main.py:391-392`
- **Description**: Tasks are `.cancel()`'d but never awaited. `CancelledError` may propagate unexpectedly, or resources held by retry tasks may not be cleaned up.
- **Impact**: Potential resource leaks or unhandled exceptions on shutdown.
- **Fix**:
  ```python
  for task in self._retry_tasks:
      task.cancel()
  if self._retry_tasks:
      await asyncio.gather(*self._retry_tasks, return_exceptions=True)
  ```

### C11. Database URL default contains hardcoded credentials
- **Files**: `src/mcp_gateway/config.py:63-66`
- **Description**: Default value `postgresql+asyncpg://echomind:echomind@localhost:5432/echomind` contains well-known credentials. If the env var override is missed in production, the service connects with these defaults. Visible in Docker image layers and config dumps.
- **Impact**: Credential leakage if env var override is missed.
- **Fix**: Use `SecretStr` type and either empty default with explicit production check, or at least log a warning if default credentials are in use.

---

## MEDIUM Issues (29)

### M1. No input validation on search tool parameters
- **Files**: `src/mcp_gateway/tools/search.py:33-35, 89`
- **Description**: `limit` accepts any int (0, negative, 999999), `score_threshold` accepts any float (negative, >1.0), empty `query=""` is allowed.
- **Impact**: OOM from huge limits, meaningless results from empty queries.
- **Fix**: Clamp `limit = max(1, min(limit, 1000))`, validate `0.0 <= score_threshold <= 1.0`, reject empty queries.

### M2. No readiness check before tool execution
- **Files**: `src/mcp_gateway/tools/search.py`, `src/mcp_gateway/tools/skills.py`, `src/mcp_gateway/tools/connectors.py`
- **Description**: Per `.claude/rules/resilience.md` rule 7: "Jobs/handlers MUST check `_is_ready()` before executing." Tools call backend methods without verifying the backend is connected.
- **Impact**: Unhandled exceptions with raw tracebacks when backends are down, instead of graceful "service unavailable" messages.
- **Fix**: Pass a readiness callback to `register_*_tools` and check it before execution, or have backend methods check their own readiness.

### M3. `SearchBackend` accesses private `_client` on QdrantDB
- **Files**: `src/mcp_gateway/backends/search_backend.py:90, 137`
- **Description**: `self._qdrant._client.get_collections()` and `self._qdrant._client.scroll()` bypass the `QdrantDB` wrapper, accessing its internal `AsyncQdrantClient` directly.
- **Impact**: Violates encapsulation. If `QdrantDB` changes internal implementation, SearchBackend breaks silently.
- **Fix**: Add `list_collections()` and `scroll()` methods to `QdrantDB` in `echomind_lib/db/qdrant.py`.

### M4. No error handling in SearchBackend methods
- **Files**: `src/mcp_gateway/backends/search_backend.py` (all methods)
- **Description**: None of the methods (`search_documents`, `list_collections`, `get_collection_info`, `get_document_chunks`) have try/except blocks. Any Qdrant error propagates as an unhandled exception.
- **Impact**: MCP tool calls fail with raw Python tracebacks instead of user-friendly error messages.
- **Fix**: Wrap each method in try/except, catch Qdrant-specific exceptions, raise domain exceptions with `from e`.

### M5. No model specified in `embed_query`
- **Files**: `src/mcp_gateway/backends/embedder_client.py:87`
- **Description**: `EmbedRequest(texts=[query])` doesn't set the `model` field. The proto has a `model` field used to select which embedding model to load.
- **Impact**: Relies on server-side default. Could embed with wrong model, causing vector dimension mismatches or poor search quality.
- **Fix**: Accept `model` parameter in `EmbedderClient.__init__` or `embed_query`, pass it in the request.

### M6. Google API key env var prefix mismatch (dual source of truth)
- **Files**: `src/mcp_gateway/config.py:83-89`, `src/mcp_gateway/backends/api_key_manager.py:14-18`
- **Description**: `config.py` defines `google_search_api_key` with `env_prefix="MCP_GATEWAY_"` (reads `MCP_GATEWAY_GOOGLE_SEARCH_API_KEY`). But `ApiKeyManager` reads `os.environ["GOOGLE_SEARCH_API_KEY"]` directly (no prefix). Docker Compose passes `GOOGLE_SEARCH_API_KEY` (no prefix). The Pydantic settings fields for Google keys are dead code.
- **Impact**: Confusion about which env vars are needed. Config.py fields never used.
- **Fix**: Remove Google key fields from `MCPGatewaySettings` (since ApiKeyManager reads them directly), or refactor ApiKeyManager to accept keys from settings.

### M7. `database_url` and `nats_password` should use `SecretStr`
- **Files**: `src/mcp_gateway/config.py:63, 77`
- **Description**: Database URL and NATS password stored as plain `str`. Visible in repr/str output, log dumps, debug output.
- **Impact**: Credential leak in repr/logs.
- **Fix**: Use `pydantic.SecretStr` and `.get_secret_value()` when needed.

### M8. DB engine not disposed before retry recreation
- **Files**: `src/mcp_gateway/main.py:296-315`
- **Description**: Each retry iteration creates a NEW `create_async_engine` without disposing the previous failed one. The old engine's connection pool is abandoned.
- **Impact**: Connection pool leak on each failed retry attempt.
- **Fix**: Dispose old engine before creating new one: `if self._db_engine: await self._db_engine.dispose()`.

### M9. `_running` flag set but never read
- **Files**: `src/mcp_gateway/main.py:287`
- **Description**: `self._running = True` is set but no code reads it to gate operations.
- **Impact**: Dead code; misleading for future developers.
- **Fix**: Either use it in tool handlers to reject requests during shutdown, or remove it.

### M10. `_validate_placeholders` only checks `${var}`, not `$var`
- **Files**: `src/mcp_gateway/skills/registry.py:168`
- **Description**: The regex `r'\$\{(\w+)\}'` only finds `${var}` placeholders, but the executor also replaces `$var` (line 96). So a skill with `command: "echo $name"` would get a "not referenced" warning even though it IS referenced.
- **Impact**: False warnings during skill loading.
- **Fix**: Remove `$var` support from executor (only support `${var}`), aligning validator and executor.

### M11. Registry docstring claims `FileNotFoundError` but returns 0
- **Files**: `src/mcp_gateway/skills/registry.py:66-72`
- **Description**: The `load()` docstring says `Raises: FileNotFoundError` but line 76 returns `0` when directory doesn't exist.
- **Impact**: Misleading API contract.
- **Fix**: Remove the `Raises` section from the docstring.

### M12. No duplicate skill name detection
- **Files**: `src/mcp_gateway/skills/registry.py:92`
- **Description**: If two skill directories contain SKILL.md files with the same `name` field, the second silently overwrites the first. No warning logged.
- **Impact**: Silent skill shadowing — hard to debug.
- **Fix**: Add check: `if skill.name in self._skills: logger.warning(f"⚠️ Duplicate skill name: {skill.name}")`.

### M13. `skills_execute` returns errors as 200 OK
- **Files**: `src/mcp_gateway/tools/skills.py:95-96`
- **Description**: When a skill is not found, the function returns `{"error": "..."}` as a normal response. MCP tools should raise an error or use a structured error pattern so the LLM client knows it failed.
- **Impact**: LLM may not recognize the call failed and continue with bad data.
- **Fix**: Raise `ValueError(f"Skill '{name}' not found")` or return with `"success": false`.

### M14. `skills_get_info` exposes raw command template
- **Files**: `src/mcp_gateway/tools/skills.py:60`
- **Description**: Returns the raw command template. For skills with hardcoded API keys or internal endpoints in commands, this would expose them to the LLM and potentially to end users.
- **Impact**: Information disclosure.
- **Fix**: Omit `command` field from response, or redact sensitive patterns.

### M15. No rate limiting on skill execution
- **Files**: `src/mcp_gateway/tools/skills.py`
- **Description**: No rate limiting on skill execution. A malicious or confused LLM could invoke expensive skills in a loop.
- **Impact**: Resource exhaustion, DoS.
- **Fix**: Add per-skill or global rate limiting (e.g., token bucket per skill name).

### M16. No resource limits in Docker Compose
- **Files**: `deployment/docker-cluster/docker-compose.yml:583-622`, `docker-compose-host.yml:649-688`
- **Description**: No `deploy.resources.limits` for CPU or memory. Skill subprocess execution can consume all host resources.
- **Impact**: DoS via resource exhaustion from runaway skill commands.
- **Fix**: Add `deploy.resources.limits: { cpus: '2.0', memory: 1G }`.

### M17. Duplicate compose definitions (base vs host)
- **Files**: Both docker-compose files
- **Description**: The host override file is a full copy of the base definition, not an override. Changes must be made in two places.
- **Impact**: Config drift between environments.
- **Fix**: Host file should only contain overrides (image tag, traefik labels). Shared config in base only.

### M18. `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` not passed in compose
- **Files**: `docker-compose.yml`, `docker-compose-host.yml`
- **Description**: `ApiKeyManager` references these env vars, but neither is listed in compose `environment:` section. Per project memory: env vars in `.env` are NOT automatically passed to containers.
- **Impact**: API keys unavailable inside container even if set in `.env`.
- **Fix**: Add to both compose files: `OPENAI_API_KEY=${OPENAI_API_KEY:-}`, `ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}`.

### M19. Audit logger missing user/session context
- **Files**: `src/mcp_gateway/middleware/audit_logger.py:156-164`
- **Description**: Audit entries capture tool name, parameters, status, duration, but NOT user/session ID, request ID, or client IP.
- **Impact**: Cannot attribute actions to users — fundamental audit requirement.
- **Fix**: Extract user/session context from MCP request context and include in audit entries.

### M20. No shell injection test in executor tests
- **Files**: `tests/unit/mcp_gateway/test_skill_executor.py`
- **Description**: No test verifies that shell metacharacters in arguments (`;`, `$()`, `` ` ``, `|`) are properly escaped by `shlex.quote()`.
- **Impact**: If `shlex.quote` usage is accidentally removed, shell injection becomes possible with no test catching it.
- **Fix**: Add `TestSkillExecutorSecurity` class with injection test cases.

### M21. Missing NATS/DB retry and stop() tests
- **Files**: `tests/unit/mcp_gateway/test_main.py`
- **Description**: Tests exist for `_retry_qdrant_connection` and `_retry_embedder_connection`, but NOT for `_retry_nats_connection`, `_retry_db_connection`, or `stop()` closing NATS/DB.
- **Impact**: Retry and cleanup logic for DB and NATS could regress silently.
- **Fix**: Add retry and stop tests for all 4 connections.

### M22. `redact_sensitive` over-redacts "key" substring
- **Files**: `src/mcp_gateway/middleware/audit_logger.py:24-26`
- **Description**: `_SENSITIVE_SUBSTRINGS` includes `"key"`, so any field containing "key" as a substring (`monkey`, `donkey`, `turkey`, `hockey`, `keyboard`) gets redacted.
- **Impact**: Data loss in audit logs for legitimate fields.
- **Fix**: Use word-boundary matching or more specific patterns: `api_key`, `secret_key`, `access_key`, `_key`, `key_`.

### M23. EchoMind internal skills use hardcoded Docker URLs
- **Files**: `config/mcp-gateway/skills/echomind-documents/SKILL.md`, `echomind-memory/SKILL.md`, `session-logs/SKILL.md`
- **Description**: Skills use `http://api:8000/api/v1/...` which is the Docker internal hostname. Fails outside Docker (local dev).
- **Impact**: Skills broken in non-Docker environments.
- **Fix**: Use `$ECHOMIND_API_URL` environment variable for base URL.

### M24. `session_factory` may be None when passed to ConnectorBackend
- **Files**: `src/mcp_gateway/main.py:256-261`
- **Description**: If PostgreSQL connection fails during startup, `self._session_factory` remains `None` but is passed to `ConnectorBackend`. The type annotation says `async_sessionmaker[AsyncSession]` (not Optional), but `None` is passed.
- **Impact**: `TypeError: 'NoneType' object is not callable` when connector tools are called while DB is down.
- **Fix**: Make `ConnectorBackend.session_factory` accept `None` and check before use, or gate tool registration behind readiness.

### M25. ConnectorBackend.trigger_sync has no real authorization
- **Files**: `src/mcp_gateway/backends/connector_backend.py:262-264`
- **Description**: `user_id` comes from MCP tool arguments (agent-provided). No auth middleware on MCP gateway, so the agent decides what `user_id` to use. LLM agent could claim to be any user.
- **Impact**: Privilege escalation — agent can trigger sync for any user's connectors.
- **Fix**: Derive `user_id` from authenticated session in Phase 8 (OAuth). Document as known limitation for now.

### M26. `NatsBackend._connected` flag not synchronized
- **Files**: `src/mcp_gateway/backends/nats_backend.py:53, 63, 87`
- **Description**: `_connected` flag set without synchronization. If `close()` is called concurrently with `publish()` during shutdown, flag check could pass but publisher could be closed mid-operation.
- **Impact**: Race condition during shutdown could cause NATS publish errors.
- **Fix**: Use `asyncio.Lock()` to synchronize connect/close/publish operations.

### M27. No `max_output_bytes` on several high-output skills
- **Files**: `github/SKILL.md`, `obsidian/SKILL.md`, `himalaya/SKILL.md`, `1password/SKILL.md`
- **Description**: Default 64KB output limit may silently truncate large outputs (PR diffs, vault searches, email content).
- **Impact**: Users get incomplete results without knowing.
- **Fix**: Add explicit `max_output_bytes` to skills that can return large output.

### M28. No auth headers in EchoMind internal API skills
- **Files**: `echomind-documents/SKILL.md`, `echomind-memory/SKILL.md`, `session-logs/SKILL.md`
- **Description**: curl commands to EchoMind's own API have no authentication headers. Either internal API doesn't require auth (security concern) or examples are incomplete (will fail with 401).
- **Impact**: Skills either bypass auth or fail silently.
- **Fix**: Clarify auth model. If needed, add Bearer token headers. If gateway injects auth, document it.

### M29. `test_main.py` start tests have 16-decorator stacking
- **Files**: `tests/unit/mcp_gateway/test_main.py:96-400`
- **Description**: Each start test uses 16 `@patch` decorators with 16+ parameters. Duplicated 4 times with minor variations. Fragile — adding a dependency requires updating all tests.
- **Impact**: Hard to read, maintain, and extend.
- **Fix**: Extract shared fixture that sets up all mocks with sane defaults.

---

## LOW Issues (22)

### L1. Truncated query log always adds `...` even for short queries
- **File**: `src/mcp_gateway/tools/search.py:52`
- **Fix**: `query[:50] + "..." if len(query) > 50 else query`

### L2. Tools return `dict[str, Any]` instead of typed models
- **Files**: `src/mcp_gateway/tools/search.py`, `tools/skills.py`
- **Impact**: MCP clients don't get structured schemas for results.

### L3. gRPC "Connected" log fires before actual connection
- **File**: `src/mcp_gateway/backends/embedder_client.py:68`
- **Fix**: Change to "Channel created for Embedder" or defer log until first successful call.

### L4. `KeyboardInterrupt` handler unreachable in asyncio
- **File**: `src/mcp_gateway/main.py:446`
- **Description**: Inside `asyncio.run()`, `KeyboardInterrupt` is converted to `CancelledError`. Dead code.
- **Fix**: Remove `except KeyboardInterrupt` block or handle `asyncio.CancelledError`.

### L5. Log level read from env AND settings (dual source)
- **File**: `src/mcp_gateway/main.py:61`
- **Description**: Uses `os.getenv("MCP_GATEWAY_LOG_LEVEL")` directly instead of `self._settings.log_level`.
- **Fix**: Use settings object as single source of truth.

### L6. No skill name format validation
- **File**: `src/mcp_gateway/skills/registry.py`
- **Description**: Skill names can contain spaces, special characters. Should validate `[a-z0-9-]+`.

### L7. Registry not thread-safe for hot reload
- **File**: `src/mcp_gateway/skills/registry.py`
- **Description**: `load()` calls `self._skills.clear()` then rebuilds. Concurrent readers see empty registry.
- **Fix**: Use lock or atomic swap pattern.

### L8. Debug log leaks interpolated commands
- **File**: `src/mcp_gateway/skills/executor.py:101`
- **Description**: Debug log prints fully interpolated command which may contain sensitive argument values.

### L9. No dangerous command pattern warnings in validator
- **File**: `scripts/validate_skills.py` (if recreated)
- **Description**: Could warn about `eval`, `bash -c`, `rm -rf`, etc.

### L10. `FakeMCP` duplicated in 4 test files
- **Files**: `test_search_tools.py`, `test_skills_tools.py`, `test_connector_tools.py`, `test_api_proxy_tools.py`
- **Fix**: Move to `conftest.py` as shared fixture.

### L11. Hardcoded skill count `42` in tests
- **Files**: `test_skill_loading.py:42`, `test_skill_e2e.py:140`
- **Fix**: Use `len(ALL_SKILL_NAMES)` or `assert count >= 40`.

### L12. Repeated registry construction in every test
- **File**: `tests/unit/mcp_gateway/test_skill_loading.py`
- **Fix**: Use `@pytest.fixture(scope="class")` for loaded registry.

### L13. Inconsistent title casing in SKILL.md headers
- **Files**: Various SKILL.md
- **Description**: `# Weather Skill` vs `# video-frames Skill` vs `# gemini Skill`.
- **Fix**: Standardize on proper case.

### L14. Tag inconsistency across skills
- **Files**: Various SKILL.md
- **Description**: No tag taxonomy. Internal details like `qdrant` used as tags. No `cli` tag for CLI wrappers.

### L15. `skill-creator` example contradicts actual weather skill
- **File**: `config/mcp-gateway/skills/skill-creator/SKILL.md`
- **Description**: Guide example uses `${command}` passthrough but actual weather skill uses structured args.
- **Fix**: Update guide to match the actual (safer) pattern.

### L16. Missing prerequisite docs on several skills
- **Files**: `nano-pdf/SKILL.md`, `wacli/SKILL.md`, `sherpa-onnx-tts/SKILL.md`, `lobster/SKILL.md`
- **Description**: No install instructions or links for required tools.

### L17. `obsidian` skill uses macOS `sed -i ''` syntax
- **File**: `config/mcp-gateway/skills/obsidian/SKILL.md`
- **Description**: BSD sed syntax. On Linux (Docker), should be `sed -i` without empty string arg.

### L18. Healthcheck defined in both Dockerfile and compose
- **Files**: `src/mcp_gateway/Dockerfile:30-31`, `docker-compose.yml:603-608`
- **Description**: Compose overrides Dockerfile healthcheck. Redundant but harmless.

### L19. `sys.path.insert` hack in main.py
- **File**: `src/mcp_gateway/main.py:39-40`
- **Description**: Path manipulation for imports. Dockerfile already sets PYTHONPATH.
- **Fix**: Remove and rely on PYTHONPATH.

### L20. `type: ignore[call-arg]` on settings instantiation
- **File**: `src/mcp_gateway/config.py:127`
- **Description**: Suppresses mypy error from Pydantic v2 metaclass. Needs explanatory comment.

### L21. Config singleton not thread-safe
- **File**: `src/mcp_gateway/config.py:118-128`
- **Description**: `get_settings()` has no lock. Unlikely race in practice but fragile pattern.

### L22. `test_config.py` dead code at line 15-16
- **File**: `tests/unit/mcp_gateway/test_config.py:15-16`
- **Description**: Loop with `pass` body — does nothing.
- **Fix**: Remove.

---

## Evaluation Scorecard

| Criteria | Score | Justification |
|----------|-------|---------------|
| **Security** | 4/10 | `create_subprocess_shell` with no sandboxing, env inheritance, `$var` prefix bug, missing `.dockerignore`, credential defaults |
| **Resilience** | 5/10 | Pattern followed correctly but stale backend references, gRPC never reconnects, retry tasks not awaited — the resilience is theater |
| **Code Quality** | 7/10 | Clean async patterns, good type hints, proper docstrings, but dead code, dual config sources, encapsulation violations |
| **Test Coverage** | 6/10 | 216 tests passing, good happy-path coverage, but `EmbedderClient` at 0%, no injection tests, incomplete retry/stop tests |
| **Docker/Deploy** | 6/10 | Good Dockerfile (non-root, healthcheck, pinned deps), but no `.dockerignore`, no resource limits, duplicate compose definitions |
| **Skill Quality** | 5/10 | Excellent documentation, but `${command}` passthrough design breaks with `shlex.quote`, no sandboxing, hardcoded Docker URLs |
| **Architecture** | 7/10 | Clean separation of concerns, good module structure, FastMCP integration solid, but trust model undefined |

**Overall: 5.7/10** — Solid foundation with professional code quality, but critical security and resilience gaps prevent production readiness.

---

## Top 3 Improvements (Priority Order)

1. **Fix `${command}` / `shlex.quote` / `$var` design** (C1+C2) — This is the #1 issue. Either introduce skill types (passthrough vs structured) with different quoting behavior, or redesign all skills to use structured args. Remove `$var` support entirely.

2. **Fix stale references + gRPC reconnection** (C3+C4+C10) — Use mutable holder pattern so backends always see current clients. Reset embedder channel on failure. Await retry tasks on shutdown.

3. **Sandbox subprocess execution** (C5+C6+C7) — Use `start_new_session=True` + `os.killpg()` for timeout kills. Pass restricted `env` dict. Set explicit `cwd`. Create `.dockerignore`. Add resource limits in compose.
