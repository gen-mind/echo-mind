# Phase 1-4 FAANG Review — Final Status

**Date**: 2026-02-17
**Branch**: `feature/agents-phase1-foundation`
**Tests**: 2559 passed, 0 failures, 2 skipped

---

## ALL FINDINGS RESOLVED

| Finding | Severity | Fix |
|---------|----------|-----|
| C1: Shell injection in git tools | CRITICAL | `shell=False` + `shlex.split()` in all 13 tools |
| H1: Session manager thread safety | HIGH | `threading.Lock` on JSONL writes |
| M1: Duplicate sandbox files | MEDIUM | Deleted 3 files from `src/agent/` |
| M2: api_proxy in tool layer | MEDIUM | Extracted `ApiProxyBackend` to `backends/` |
| M3: SANDBOX_ENABLED flag | MEDIUM | Removed — sandbox always on, `pool_size` ge=1 |
| M4: embedder_client %s logging | MEDIUM | Converted to f-strings |
| L1: NET_RAW capability | LOW | Removed `cap_add=["NET_RAW"]` |
| L2: Redundant exception catches | LOW | Collapsed to `except Exception` |
| L3: Persistence error tracking | LOW | Added `_persistence_errors` counter |
| L4: list.pop(0) warm pool | LOW | Replaced with `deque.popleft()` |

## Additional Fixes (Pre-existing Test Failures)

| Area | Tests Fixed | Root Cause |
|------|-------------|------------|
| Google scopes | 12 | Tests expected `.readonly` scopes, source uses broad scopes |
| Permissions | 11 | Tests set `user.roles`, source checks `user.groups` |
| Connector service | 1 | Source raises `ServiceUnavailableError`, test expected tuple |
| Connector endpoints | 2 | Missing `echomind-allowed` group in mock user |
| Document endpoints | 2 | Missing Qdrant/MinIO dependency overrides |
| Upload service | 1 | Same ServiceUnavailableError pattern |
| Embedder | 3 | MIN_TEXT_LENGTH=50 validation, tests used 5-char strings |

## Agent Docs Cleanup

- **Deleted**: `old-agent-phases-roadmap.md`
- **Cleaned**: 10 docs — removed Phase 5-8+ future references, kept Phase 1-4 content
