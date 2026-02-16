# Anthropic LLM Provider Support — Analysis & Implementation TODO

> **Date:** 2026-02-16
> **Status:** Analysis complete, implementation not started
> **Estimated effort:** 3/10 difficulty, 2-4 hours

---

## Executive Summary

Adding Anthropic (Claude) as an LLM provider to the EchoMind agent system is **straightforward**. The Microsoft Agent Framework (`agent-framework`) already ships a first-class `AnthropicClient` with identical interfaces to `OpenAIChatClient`. All 30 tools, 9-layer policy engine, middleware, MCP integration, and session management work unchanged.

---

## Current State

### What exists today

| Component | Provider support | Location |
|-----------|-----------------|----------|
| `BasicAgentWrapper` | OpenAI only (`OpenAIChatClient`) | `src/agent/agent.py:19,124` |
| `IntentClassifier` | OpenAI only (`AsyncOpenAI`) | `src/agent/routing/intent.py:72-83` |
| `detect_provider()` | Detects `"anthropic"` from `"claude-"` prefix | `src/agent/policy/providers.py:20-23` |
| `ToolPolicy.by_provider` | Has `"anthropic"` key in config | `config/agents/config.yaml:14` |
| `config.yaml` agents | All use `${OPENAI_MODEL:-gpt-4o-mini}` | `config/agents/config.yaml:22,34,52` |

### Key insight

Provider detection and provider-aware policy filtering already exist — they were built for tool access control. The only missing piece is **using the detected provider to create the correct LLM client**.

---

## Framework Support (Verified)

The Microsoft Agent Framework provides `AnthropicClient` as a drop-in replacement:

```python
# Current (OpenAI only)
from agent_framework.openai import OpenAIChatClient
client = OpenAIChatClient(model_id="gpt-4o-mini", api_key=key)

# Anthropic equivalent (identical interface)
from agent_framework.anthropic import AnthropicClient
client = AnthropicClient(model_id="claude-sonnet-4-5-20250929", api_key=key)
```

**Both clients implement the same base class** — same `get_response()`, `get_streaming_response()`, `create_agent()`, same middleware contracts, same `ToolProtocol`.

### Installation

```bash
pip install agent-framework-anthropic --pre
# Requires: anthropic>=0.74.0
```

### Environment variables

```bash
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_CHAT_MODEL_ID="claude-sonnet-4-5-20250929"
```

### Sources

- [AnthropicClient API — Microsoft Learn](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.anthropic.anthropicclient?view=agent-framework-python-latest) (updated 2026-01-08)
- [Anthropic Agents Tutorial — Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/anthropic-agent) (updated 2026-02-13)
- [Microsoft Agent Framework — GitHub](https://github.com/microsoft/agent-framework)

---

## Implementation TODO

### 1. Add dependencies

**File:** `src/agent/requirements.txt`

```
agent-framework-anthropic==1.0.0b260212
anthropic>=0.74.0
```

### 2. Modify `BasicAgentWrapper` to support both providers

**File:** `src/agent/agent.py`

Changes needed (~20 lines):
- Import `AnthropicClient` from `agent_framework.anthropic`
- Use `detect_provider(config.model)` to branch client creation
- Support `ANTHROPIC_API_KEY` env var alongside `OPENAI_API_KEY`
- Allow per-agent `api_key` override in config

```python
from agent.policy.providers import detect_provider

provider = detect_provider(config.model)
if provider == "anthropic":
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    self.client = AnthropicClient(model_id=config.model, api_key=api_key)
elif provider == "openai":
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    client_kwargs = {"model_id": config.model, "api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    self.client = OpenAIChatClient(**client_kwargs)
else:
    # Local/custom — use OpenAI-compatible with base_url
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    self.client = OpenAIChatClient(model_id=config.model, api_key=api_key, base_url=base_url)
```

### 3. Update config schema

**File:** `src/agent/config/schema.py`

Add optional fields to `AgentConfig`:
- `provider: str | None` — Override auto-detection ("openai", "anthropic", "local")
- `api_key_env: str | None` — Custom env var name for API key (e.g., `"MY_CLAUDE_KEY"`)

### 4. Update config YAML with Anthropic agent example

**File:** `config/agents/config.yaml`

```yaml
- id: claude-assistant
  name: "Claude Assistant"
  model: "claude-sonnet-4-5-20250929"
  # Provider auto-detected from "claude-" prefix
  instructions: |
    You are a helpful AI assistant powered by Claude.
  tools:
    profile: full
```

### 5. IntentClassifier — decide strategy

**File:** `src/agent/routing/intent.py`

Options (pick one):
- **Option A (recommended):** Keep using OpenAI for classification. It's a lightweight utility call, not user-facing. Simplest approach.
- **Option B:** Abstract to use the Agent Framework's client. More correct but more work.
- **Option C:** Support both providers. Most flexible but over-engineered for a routing utility.

### 6. Update AgentFactory credential resolution

**File:** `src/agent/agent.py` (`AgentFactory` class)

The factory currently passes a single `api_key` to all agents. With multi-provider support, it needs to:
- Accept both `openai_api_key` and `anthropic_api_key`
- Or resolve from env vars per-agent based on detected provider

### 7. Verify response extraction

**File:** `src/agent/agent.py` (lines 241-263 in `run()`)

The response extraction uses `hasattr` checks. Verify that `AnthropicClient` returns the same `ChatResponse` type with identical field names:
- `response.content` — text content
- `response.finish_reason` — completion reason
- `response.usage.prompt_tokens` / `completion_tokens` / `total_tokens`
- `response.tool_calls` — tool call results

**Risk:** Low — the framework normalizes responses, but needs integration testing.

### 8. Add tests

**Files:** `tests/unit/agent/test_agent.py` + new `tests/unit/agent/test_provider_routing.py`

Test cases needed:
- Provider detection routes to correct client class
- Anthropic API key resolved from `ANTHROPIC_API_KEY`
- OpenAI API key resolved from `OPENAI_API_KEY`
- Missing API key raises `ValueError` with correct env var name
- Config with `provider` override bypasses auto-detection
- Mixed-provider agent list (one OpenAI, one Anthropic) works
- Policy engine `by_provider` filtering still works correctly
- Streaming with Anthropic client (mock)

---

## What Requires Zero Changes

| Component | Why it works unchanged |
|-----------|----------------------|
| All 30 tools | Same `ToolProtocol` interface, provider-agnostic |
| 9-layer policy engine | Already has `by_provider` support, `detect_provider()` exists |
| `ToolPolicyMiddleware` | Operates on `ChatContext`, provider-independent |
| `PathRestrictionMiddleware` | Operates on `FunctionInvocationContext`, provider-independent |
| Session management (JSONL) | Stores role/content strings, provider-independent |
| `JSONLHistoryProvider` | Uses framework's `ContextProvider` interface |
| MCP integration | MCP tools implement same `ToolProtocol` |
| Routing system | Routes by agent ID, not by provider |
| Config parser | Already handles `byProvider` in `ToolPolicy` |

---

## Comparison with Moltbot

| Aspect | Moltbot approach | EchoMind approach |
|--------|-----------------|-------------------|
| Provider abstraction | Custom per-provider API format handling (`anthropic-messages` vs `openai-compatible`) | Framework handles it (`AnthropicClient` vs `OpenAIChatClient`) |
| Tool schema normalization | Manual `patchToolSchemaForClaudeCompatibility()` | Framework handles internally |
| Auth management | Auth profiles with OAuth, token exchange, fallback chains | Simple env var per provider |
| Effort to add Anthropic | ~500+ lines of TypeScript | ~50 lines of Python |

**Why the gap?** Moltbot uses a lower-level framework (Pi Agent) that doesn't abstract provider differences. EchoMind uses Microsoft Agent Framework which provides identical interfaces across providers.

---

## Design Decisions (Resolved)

| Decision | Answer | Notes |
|----------|--------|-------|
| **Mixed-provider agents** | **No** (for now) | Single provider per deployment. Add as future feature when needed. |
| **Provider failover** | **No** (phase 1) | Defer to phase 9 with circuit breakers. |
| **Extended thinking** | **Defer** | Phase 8+. |
| **Azure Foundry** | **Defer** | Not relevant for current deployment. |
| **Response object diff** | **Defer** | Future investigation. Framework normalizes; verify during integration testing. |
| **Cost/token tracking** | **Langfuse direct SDK** | No custom cost tracking — Langfuse handles pricing per model. |
| **OTEL Collector** | **No** (future feature) | No collector service for now. Send traces directly to Langfuse via SDK and metrics to Prometheus, matching the existing codebase pattern. |

### Observability Requirement (Mandatory)

**No OTEL Collector.** Follow the existing EchoMind pattern:

1. **Langfuse SDK** (direct) — LLM generation tracking with token counts, cost, latency, and `session_id` for conversation-level grouping. Use `echomind_lib.helpers.langfuse_helper` (`create_trace()`, `score_trace()`).
2. **Prometheus** (direct) — Service metrics exposed at `/metrics`, scraped by Prometheus. Use `prometheus_client` like `src/api/middleware/metrics.py`.

This matches how existing services already work:
- API service: `langfuse_helper.create_trace()` in `chat_handler.py`
- API service: `prometheus_client` histograms/counters in `metrics.py`
- Ingestor/Connector: `init_langfuse()` on startup

Both MCP gateway and agent service MUST send Langfuse traces with `session_id`, `agent_id`, `provider`, and `model` attributes. Langfuse natively supports both OpenAI and Anthropic token pricing.

**OTEL Collector is a future feature** — useful later for ephemeral sandbox containers that can't guarantee flush before termination. For in-process agents (current architecture), direct SDK is simpler and sufficient.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Response format mismatch | Low | Medium | Framework normalizes; integration test to verify |
| Streaming chunk differences | Low | Low | Framework normalizes; test with mock |
| `agent-framework-anthropic` beta instability | Medium | Medium | Pin exact version, test thoroughly |
| Tool schema edge cases | Very Low | Low | Framework handles; all 30 tools use standard annotations |
| `anthropic` package conflicts with other services | Low | Medium | Agent runs in its own service; isolated deps |
