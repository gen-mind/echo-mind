"""Tests for sandbox AgentRunner, AgentMetrics, and QueryContext."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from sandbox.agent_runner import AgentMetrics, AgentRunner, QueryContext
from sandbox.config import SandboxSettings


# ── AgentMetrics ──────────────────────────────────────────────


class TestAgentMetrics:
    """Tests for the AgentMetrics dataclass."""

    def test_defaults(self) -> None:
        """Test default metric values."""
        m = AgentMetrics()
        assert m.message_count == 0
        assert m.tool_calls_count == 0
        assert m.total_tokens == 0
        assert m.error_count == 0

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        m = AgentMetrics(message_count=3, tool_calls_count=2, total_tokens=500, error_count=1)
        d = m.to_dict()
        assert d == {
            "message_count": 3,
            "tool_calls_count": 2,
            "total_tokens": 500,
            "error_count": 1,
        }

    def test_mutation(self) -> None:
        """Test that metric fields can be incremented."""
        m = AgentMetrics()
        m.message_count += 1
        m.total_tokens += 100
        assert m.message_count == 1
        assert m.total_tokens == 100


# ── QueryContext ──────────────────────────────────────────────


class TestQueryContext:
    """Tests for the QueryContext dataclass."""

    def test_minimal_creation(self) -> None:
        """Test creating a QueryContext with just a query."""
        ctx = QueryContext(query="Hello")
        assert ctx.query == "Hello"
        assert ctx.conversation_history == []
        assert ctx.sources == []
        assert ctx.metadata == {}

    def test_full_creation(self) -> None:
        """Test creating a QueryContext with all fields."""
        history = [{"role": "user", "content": "Hi"}]
        ctx = QueryContext(
            query="Follow up",
            conversation_history=history,
            sources=["collection-a"],
            metadata={"key": "val"},
        )
        assert ctx.query == "Follow up"
        assert ctx.conversation_history == history
        assert ctx.sources == ["collection-a"]
        assert ctx.metadata == {"key": "val"}

    def test_mutable_defaults_are_independent(self) -> None:
        """Test that each instance gets its own mutable defaults."""
        a = QueryContext(query="a")
        b = QueryContext(query="b")
        a.sources.append("x")
        assert b.sources == []


# ── AgentRunner ───────────────────────────────────────────────


def _make_settings(**overrides: str | int) -> SandboxSettings:
    """Create SandboxSettings with sensible test defaults.

    Args:
        **overrides: Field name -> value overrides.

    Returns:
        Configured SandboxSettings.
    """
    defaults = {
        "session_id": "test-session",
        "user_id": 1,
        "mode": "active",
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
    }
    defaults.update(overrides)
    return SandboxSettings(**defaults)


class TestAgentRunnerInit:
    """Tests for AgentRunner initialization."""

    def test_subjects_derived_from_session(self) -> None:
        """Test that NATS subjects use the session_id."""
        settings = _make_settings(session_id="sess-42")
        nc = MagicMock()
        runner = AgentRunner(settings, nc)
        assert runner._output_subject == "sandbox.sess-42.output"
        assert runner._stream_subject == "sandbox.sess-42.stream"

    def test_initial_state(self) -> None:
        """Test that runner starts uninitialized with zero metrics."""
        settings = _make_settings()
        nc = MagicMock()
        runner = AgentRunner(settings, nc)
        assert runner._initialized is False
        assert runner.metrics.message_count == 0

    @pytest.mark.asyncio
    async def test_initialize_sets_flag(self) -> None:
        """Test that initialize() sets the initialized flag."""
        settings = _make_settings()
        nc = MagicMock()
        runner = AgentRunner(settings, nc)
        await runner.initialize()
        assert runner._initialized is True


class TestAgentRunnerProcessQuery:
    """Tests for query processing."""

    @pytest.mark.asyncio
    async def test_process_query_not_initialized_raises(self) -> None:
        """Test that processing without initialize() raises RuntimeError."""
        settings = _make_settings()
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)
        ctx = QueryContext(query="Hello")
        with pytest.raises(RuntimeError, match="not initialized"):
            await runner.process_query(ctx)

    @pytest.mark.asyncio
    async def test_process_query_publishes_tokens(self) -> None:
        """Test that process_query publishes stream tokens and completion."""
        settings = _make_settings(session_id="sess-1")
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)
        await runner.initialize()

        ctx = QueryContext(query="Hello world")
        await runner.process_query(ctx)

        # Should have published at least 2 messages (token + complete on stream)
        # and 1 on output
        calls = nc.publish.call_args_list
        assert len(calls) >= 2

        # Check stream subject used
        subjects = [c[0][0] for c in calls]
        assert "sandbox.sess-1.stream" in subjects
        assert "sandbox.sess-1.output" in subjects

    @pytest.mark.asyncio
    async def test_process_query_increments_metrics(self) -> None:
        """Test that metrics are updated after processing."""
        settings = _make_settings()
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)
        await runner.initialize()

        ctx = QueryContext(query="Count my tokens")
        await runner.process_query(ctx)

        assert runner.metrics.message_count == 1
        assert runner.metrics.total_tokens > 0

    @pytest.mark.asyncio
    async def test_process_query_multiple_messages(self) -> None:
        """Test message_count increments with each query."""
        settings = _make_settings()
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)
        await runner.initialize()

        for _ in range(3):
            await runner.process_query(QueryContext(query="Hi"))

        assert runner.metrics.message_count == 3


class TestAgentRunnerPublishing:
    """Tests for NATS publishing methods."""

    @pytest.mark.asyncio
    async def test_publish_stream_token(self) -> None:
        """Test _publish_stream_token publishes correct payload."""
        settings = _make_settings(session_id="sess-pub")
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)

        await runner._publish_stream_token("hello")

        nc.publish.assert_awaited_once()
        subject, payload = nc.publish.call_args[0]
        assert subject == "sandbox.sess-pub.stream"
        data = json.loads(payload)
        assert data["type"] == "token"
        assert data["data"] == "hello"

    @pytest.mark.asyncio
    async def test_publish_complete(self) -> None:
        """Test _publish_complete publishes to stream and output."""
        settings = _make_settings(session_id="sess-comp")
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)

        await runner._publish_complete("Full response text")

        assert nc.publish.call_count == 2
        calls = nc.publish.call_args_list

        # First call: stream subject
        stream_subject, stream_payload = calls[0][0]
        assert stream_subject == "sandbox.sess-comp.stream"
        stream_data = json.loads(stream_payload)
        assert stream_data["type"] == "complete"
        assert stream_data["data"] == "Full response text"

        # Second call: output subject
        output_subject, output_payload = calls[1][0]
        assert output_subject == "sandbox.sess-comp.output"
        output_data = json.loads(output_payload)
        assert output_data["type"] == "response"
        assert output_data["content"] == "Full response text"

    @pytest.mark.asyncio
    async def test_publish_error(self) -> None:
        """Test _publish_error publishes error event."""
        settings = _make_settings(session_id="sess-err")
        nc = AsyncMock()
        runner = AgentRunner(settings, nc)

        await runner._publish_error("Something went wrong")

        nc.publish.assert_awaited_once()
        subject, payload = nc.publish.call_args[0]
        assert subject == "sandbox.sess-err.stream"
        data = json.loads(payload)
        assert data["type"] == "error"
        assert data["error"] == "Something went wrong"


class TestAgentRunnerShutdown:
    """Tests for agent runner shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_resets_initialized(self) -> None:
        """Test that shutdown() clears the initialized flag."""
        settings = _make_settings()
        nc = MagicMock()
        runner = AgentRunner(settings, nc)
        await runner.initialize()
        assert runner._initialized is True

        await runner.shutdown()
        assert runner._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self) -> None:
        """Test that calling shutdown() twice is safe."""
        settings = _make_settings()
        nc = MagicMock()
        runner = AgentRunner(settings, nc)
        await runner.shutdown()
        await runner.shutdown()
        assert runner._initialized is False
