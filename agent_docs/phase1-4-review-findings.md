# Phase 1-4 FAANG Review Findings

**Date**: 2026-02-17
**Branch**: `feature/agents-phase1-foundation`
**Reviewers**: 8 parallel agents (4 deferred-feature hunters + 3 code reviewers + 1 test runner)

---

## Status: ALL FIXED

All findings below have been resolved. 1044 tests passing (0 failures) across agent, sandbox, and mcp_gateway suites.

| Finding | Severity | Status |
|---------|----------|--------|
| C1: Shell injection in git tools | CRITICAL | FIXED |
| H1: Session manager thread safety | HIGH | FIXED |
| M1: Duplicate sandbox files in src/agent/ | MEDIUM | FIXED |
| M2: api_proxy business logic in tool layer | MEDIUM | FIXED |
| M3: SANDBOX_ENABLED removed, always on | MEDIUM | FIXED |
| M4: embedder_client %s logging | MEDIUM | FIXED |
| L1: cap_add=NET_RAW | LOW | DEFERRED (user decision) |
| L2: Redundant (APIError, Exception) catches | LOW | FIXED |
| L3: Persistence error tracking | LOW | FIXED |
| L4: list.pop(0) replaced with deque | LOW | FIXED |

---

## Deferred Feature Audit: CLEAN

No unauthorized implementations found. All Phase 8+ features confirmed absent.

---

## Fix Details

### C1 — Shell injection in git tools (FIXED)
- `src/agent/tools/git.py`: All 5 functions converted from `shell=True` + f-strings to `shell=False` + list args with `shlex.split()`
- `src/agent/tools/git_extended.py`: All 8 functions converted similarly
- 12 new injection tests added (semicolons, `$()`, backticks, pipes)

### H1 — Session manager thread safety (FIXED)
- `src/agent/sessions/manager.py`: Added `threading.Lock` wrapping `_append_entry` file writes

### M1 — Duplicate sandbox files deleted (FIXED)
- Deleted `src/agent/sandbox_runner.py`, `src/agent/sandbox_config.py`, `src/agent/Dockerfile`

### M2 — api_proxy backend extraction (FIXED)
- Created `src/mcp_gateway/backends/api_proxy_backend.py` with `ApiProxyBackend` class
- `src/mcp_gateway/tools/api_proxy.py` is now a thin adapter
- 9 new backend tests added

### M3 — SANDBOX_ENABLED removed (FIXED)
- Removed `enabled` field from `SandboxSettings`
- `pool_size` now has `ge=1` (minimum 1 warm container always running)
- Removed SANDBOX_ENABLED from docker-compose files and .env.example
- `cluster.sh` now unconditionally includes sandbox compose files

### M4 — embedder_client f-strings (FIXED)
- Converted remaining `%s` log lines to f-strings

### L1 — cap_add=NET_RAW (DEFERRED)
- Needs verification whether sandbox containers require raw sockets

### L2 — Redundant exception catches (FIXED)
- All 7 `except (APIError, Exception)` collapsed to `except Exception` in docker_backend.py

### L3 — Persistence error tracking (FIXED)
- Added `_persistence_errors` counter to SandboxManager
- Exposed in `get_status()` response

### L4 — deque for warm pool (FIXED)
- `_warm_pool` changed from `list` to `collections.deque`
- `pop(0)` replaced with `popleft()` (O(1) vs O(n))
