"""Tests for SandboxAgent (src/sandbox/main.py).

Tests cover initialization, readiness, warm/active modes, message handling,
heartbeat loop, and graceful shutdown -- all with mocked NATS and HealthServer.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sandbox.config import SandboxSettings
from sandbox.main import SandboxAgent


def _make_settings(**overrides: str | int) -> SandboxSettings:
    """Create SandboxSettings with sensible test defaults.

    Args:
        **overrides: Field name -> value overrides.

    Returns:
        Configured SandboxSettings.
    """
    defaults: dict[str, str | int] = {
        "nats_url": "nats://test:4222",
        "session_id": "sess-1",
        "user_id": 42,
        "mode": "active",
        "health_port": 0,
        "heartbeat_interval": 1,
    }
    defaults.update(overrides)
    return SandboxSettings(**defaults)


def _make_mock_msg(data: dict) -> MagicMock:
    """Create a mock NATS Msg with encoded JSON data.

    Args:
        data: JSON-serializable payload.

    Returns:
        MagicMock with .data attribute.
    """
    msg = MagicMock()
    msg.data = json.dumps(data).encode("utf-8")
    return msg


# ── Initialization & Readiness ────────────────────────────────


class TestSandboxAgentInit:
    """Tests for SandboxAgent initialization."""

    def test_default_construction(self) -> None:
        """Test SandboxAgent with default settings."""
        agent = SandboxAgent()
        assert agent.settings is not None
        assert agent._running is True
        assert agent._ready is False
        assert agent._nats_connected is False

    def test_custom_settings(self) -> None:
        """Test SandboxAgent with explicit settings."""
        settings = _make_settings(session_id="custom")
        agent = SandboxAgent(settings)
        assert agent.settings.session_id == "custom"

    def test_is_ready_false_by_default(self) -> None:
        """Test _is_ready() returns False before connection."""
        agent = SandboxAgent(_make_settings())
        assert agent._is_ready() is False

    def test_is_ready_requires_both_flags(self) -> None:
        """Test _is_ready() requires NATS connected AND ready flag."""
        agent = SandboxAgent(_make_settings())
        agent._nats_connected = True
        assert agent._is_ready() is False  # _ready still False

        agent._ready = True
        assert agent._is_ready() is True

    def test_update_readiness_calls_health_server(self) -> None:
        """Test _update_readiness() propagates to health server."""
        agent = SandboxAgent(_make_settings())
        mock_hs = MagicMock()
        agent._health_server = mock_hs

        agent._nats_connected = True
        agent._ready = True
        agent._update_readiness()
        mock_hs.set_ready.assert_called_with(True)

        agent._nats_connected = False
        agent._update_readiness()
        mock_hs.set_ready.assert_called_with(False)

    def test_update_readiness_without_health_server(self) -> None:
        """Test _update_readiness() is safe when health server is None."""
        agent = SandboxAgent(_make_settings())
        agent._health_server = None
        # Should not raise
        agent._update_readiness()


# ── Start (mocked NATS) ──────────────────────────────────────


class TestSandboxAgentStart:
    """Tests for SandboxAgent.start() with mocked external deps."""

    @pytest.mark.asyncio
    async def test_start_active_mode_connects_nats(self) -> None:
        """Test start() in active mode connects NATS and activates."""
        settings = _make_settings(mode="active", session_id="sess-active")
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.subscribe = AsyncMock()
        mock_nc.publish = AsyncMock()
        mock_nc.is_closed = False

        with patch("sandbox.main.nats") as mock_nats_mod, \
             patch("sandbox.main.HealthServer") as mock_hs_cls:
            mock_nats_mod.connect = AsyncMock(return_value=mock_nc)
            mock_nc.jetstream.return_value = AsyncMock()
            mock_hs_cls.return_value = MagicMock()

            await agent.start()

            assert agent._nats_connected is True
            assert agent._ready is True
            assert agent._agent_runner is not None
            # NATS subscribe called for input + control
            assert mock_nc.subscribe.call_count == 2
            # Ready signal published
            mock_nc.publish.assert_called()

    @pytest.mark.asyncio
    async def test_start_warm_mode(self) -> None:
        """Test start() in warm mode subscribes to warm control subject."""
        settings = _make_settings(mode="warm", session_id="")
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.subscribe = AsyncMock()
        mock_nc.is_closed = False

        with patch("sandbox.main.nats") as mock_nats_mod, \
             patch("sandbox.main.HealthServer") as mock_hs_cls:
            mock_nats_mod.connect = AsyncMock(return_value=mock_nc)
            mock_nc.jetstream.return_value = AsyncMock()
            mock_hs_cls.return_value = MagicMock()

            await agent.start()

            assert agent._nats_connected is True
            assert agent._ready is True  # warm containers are ready
            # Should subscribe to sandbox.warm.control
            mock_nc.subscribe.assert_called_once()
            call_args = mock_nc.subscribe.call_args
            assert call_args[0][0] == "sandbox.warm.control"

    @pytest.mark.asyncio
    async def test_start_nats_failure_retries_in_background(self) -> None:
        """Test that NATS failure during start spawns a retry task."""
        settings = _make_settings(mode="active")
        agent = SandboxAgent(settings)

        with patch("sandbox.main.nats") as mock_nats_mod, \
             patch("sandbox.main.HealthServer") as mock_hs_cls:
            mock_nats_mod.connect = AsyncMock(side_effect=Exception("Connection refused"))
            mock_hs_cls.return_value = MagicMock()

            await agent.start()

            assert agent._nats_connected is False
            assert len(agent._retry_tasks) == 1
            # Cancel the retry task to avoid dangling
            agent._retry_tasks[0].cancel()


# ── Warm Mode Control Handling ────────────────────────────────


class TestSandboxAgentWarmControl:
    """Tests for warm mode assignment handling."""

    @pytest.mark.asyncio
    async def test_handle_warm_assign(self) -> None:
        """Test assign control message transitions to active mode."""
        settings = _make_settings(mode="warm", session_id="")
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.subscribe = AsyncMock()
        mock_nc.publish = AsyncMock()
        mock_nc.is_closed = False
        agent._nc = mock_nc
        agent._nats_connected = True

        # Add a mock subscription for unsubscribe
        mock_sub = AsyncMock()
        agent._subscriptions.append(mock_sub)

        msg = _make_mock_msg({
            "type": "assign",
            "session_id": "sess-new",
            "user_id": 99,
            "llm_provider": "anthropic",
            "llm_model": "claude-3",
        })

        await agent._handle_warm_control(msg)

        assert agent.settings.session_id == "sess-new"
        assert agent.settings.user_id == 99
        assert agent.settings.mode == "active"
        assert agent.settings.llm_provider == "anthropic"
        assert agent.settings.llm_model == "claude-3"
        assert agent._agent_runner is not None
        assert agent._ready is True

        # Old subscription was unsubscribed
        mock_sub.unsubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_warm_shutdown(self) -> None:
        """Test shutdown control message stops the agent."""
        agent = SandboxAgent(_make_settings(mode="warm"))
        agent._running = True

        msg = _make_mock_msg({"type": "shutdown"})
        await agent._handle_warm_control(msg)

        assert agent._running is False

    @pytest.mark.asyncio
    async def test_handle_warm_invalid_json(self) -> None:
        """Test invalid JSON in warm control doesn't crash."""
        agent = SandboxAgent(_make_settings(mode="warm"))
        msg = MagicMock()
        msg.data = b"not json"
        # Should not raise
        await agent._handle_warm_control(msg)


# ── Input Message Handling ────────────────────────────────────


class TestSandboxAgentInputHandling:
    """Tests for _handle_input message handler."""

    @pytest.mark.asyncio
    async def test_handle_input_query(self) -> None:
        """Test input message dispatches to agent runner."""
        settings = _make_settings(session_id="sess-in")
        agent = SandboxAgent(settings)
        agent._running = True

        mock_runner = AsyncMock()
        mock_runner.process_query = AsyncMock()
        agent._agent_runner = mock_runner

        msg = _make_mock_msg({
            "type": "query",
            "query": "What is 2+2?",
            "conversation_history": [],
            "sources": ["math"],
            "metadata": {"key": "val"},
        })

        await agent._handle_input(msg)

        mock_runner.process_query.assert_awaited_once()
        ctx = mock_runner.process_query.call_args[0][0]
        assert ctx.query == "What is 2+2?"
        assert ctx.sources == ["math"]
        assert ctx.metadata == {"key": "val"}

    @pytest.mark.asyncio
    async def test_handle_input_skipped_when_not_running(self) -> None:
        """Test input messages are ignored when not running."""
        agent = SandboxAgent(_make_settings())
        agent._running = False
        mock_runner = AsyncMock()
        agent._agent_runner = mock_runner

        msg = _make_mock_msg({"type": "query", "query": "Hi"})
        await agent._handle_input(msg)

        mock_runner.process_query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_input_skipped_when_no_runner(self) -> None:
        """Test input messages are ignored when agent runner is None."""
        agent = SandboxAgent(_make_settings())
        agent._running = True
        agent._agent_runner = None

        msg = _make_mock_msg({"type": "query", "query": "Hi"})
        # Should not raise
        await agent._handle_input(msg)

    @pytest.mark.asyncio
    async def test_handle_input_invalid_json(self) -> None:
        """Test invalid JSON in input message doesn't crash."""
        agent = SandboxAgent(_make_settings())
        agent._running = True
        agent._agent_runner = AsyncMock()

        msg = MagicMock()
        msg.data = b"bad json"
        # Should not raise
        await agent._handle_input(msg)

    @pytest.mark.asyncio
    async def test_handle_input_unknown_type(self) -> None:
        """Test unknown input type is logged, not processed."""
        agent = SandboxAgent(_make_settings())
        agent._running = True
        mock_runner = AsyncMock()
        agent._agent_runner = mock_runner

        msg = _make_mock_msg({"type": "unknown_type"})
        await agent._handle_input(msg)

        mock_runner.process_query.assert_not_awaited()


# ── Control Message Handling ──────────────────────────────────


class TestSandboxAgentControlHandling:
    """Tests for _handle_control message handler."""

    @pytest.mark.asyncio
    async def test_handle_control_shutdown(self) -> None:
        """Test shutdown control sets running to False."""
        agent = SandboxAgent(_make_settings())
        agent._running = True

        msg = _make_mock_msg({"type": "shutdown"})
        await agent._handle_control(msg)

        assert agent._running is False

    @pytest.mark.asyncio
    async def test_handle_control_cancel(self) -> None:
        """Test cancel control is handled without error."""
        agent = SandboxAgent(_make_settings())
        agent._running = True

        msg = _make_mock_msg({"type": "cancel"})
        # Should not raise
        await agent._handle_control(msg)
        # Running should still be True (cancel doesn't stop agent)
        assert agent._running is True

    @pytest.mark.asyncio
    async def test_handle_control_unknown(self) -> None:
        """Test unknown control type is handled gracefully."""
        agent = SandboxAgent(_make_settings())
        msg = _make_mock_msg({"type": "magic_command"})
        # Should not raise
        await agent._handle_control(msg)

    @pytest.mark.asyncio
    async def test_handle_control_invalid_json(self) -> None:
        """Test invalid JSON in control message doesn't crash."""
        agent = SandboxAgent(_make_settings())
        msg = MagicMock()
        msg.data = b"not{json"
        # Should not raise
        await agent._handle_control(msg)


# ── Heartbeat ─────────────────────────────────────────────────


class TestSandboxAgentHeartbeat:
    """Tests for the heartbeat loop."""

    @pytest.mark.asyncio
    async def test_heartbeat_publishes_to_health_subject(self) -> None:
        """Test heartbeat publishes correct subject and payload."""
        settings = _make_settings(session_id="sess-hb", heartbeat_interval=0)
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.is_closed = False
        mock_nc.publish = AsyncMock()
        agent._nc = mock_nc

        # Run one iteration then stop
        agent._running = True

        import asyncio

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.05)
            agent._running = False

        stop_task = asyncio.create_task(stop_after_delay())
        await agent._heartbeat_loop()
        await stop_task

        # Should have published at least one heartbeat
        assert mock_nc.publish.call_count >= 1
        # Check the first publish call (when _running was still True)
        subject, payload = mock_nc.publish.call_args_list[0][0]
        assert subject == "sandbox.sess-hb.health"
        data = json.loads(payload)
        assert data["type"] == "heartbeat"
        assert data["session_id"] == "sess-hb"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_heartbeat_skips_when_nats_closed(self) -> None:
        """Test heartbeat skips publish when NATS is disconnected."""
        settings = _make_settings(heartbeat_interval=0)
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.is_closed = True
        agent._nc = mock_nc

        import asyncio

        agent._running = True

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.05)
            agent._running = False

        stop_task = asyncio.create_task(stop_after_delay())
        await agent._heartbeat_loop()
        await stop_task

        mock_nc.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heartbeat_includes_metrics(self) -> None:
        """Test heartbeat includes agent runner metrics when available."""
        settings = _make_settings(session_id="sess-m", heartbeat_interval=0)
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.is_closed = False
        mock_nc.publish = AsyncMock()
        agent._nc = mock_nc

        # Set up a runner with some metrics
        from sandbox.agent_runner import AgentMetrics, AgentRunner
        mock_runner = MagicMock(spec=AgentRunner)
        mock_runner.metrics = AgentMetrics(message_count=5, total_tokens=100)
        agent._agent_runner = mock_runner

        import asyncio

        agent._running = True

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.05)
            agent._running = False

        stop_task = asyncio.create_task(stop_after_delay())
        await agent._heartbeat_loop()
        await stop_task

        _, payload = mock_nc.publish.call_args[0]
        data = json.loads(payload)
        assert data["metrics"]["message_count"] == 5
        assert data["metrics"]["total_tokens"] == 100


# ── Stop / Graceful Shutdown ─────────────────────────────────


class TestSandboxAgentStop:
    """Tests for SandboxAgent.stop() graceful shutdown."""

    @pytest.mark.asyncio
    async def test_stop_sets_not_running(self) -> None:
        """Test stop() sets _running to False."""
        agent = SandboxAgent(_make_settings())
        agent._running = True
        agent._nc = None
        agent._health_server = None
        await agent.stop()
        assert agent._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat(self) -> None:
        """Test stop() cancels the heartbeat task."""
        import asyncio

        agent = SandboxAgent(_make_settings())
        agent._nc = None
        agent._health_server = None

        # Create a dummy heartbeat task
        async def dummy_loop() -> None:
            while True:
                await asyncio.sleep(100)

        agent._heartbeat_task = asyncio.create_task(dummy_loop())
        await agent.stop()
        assert agent._heartbeat_task.cancelled() or agent._heartbeat_task.done()

    @pytest.mark.asyncio
    async def test_stop_publishes_destroy_event(self) -> None:
        """Test stop() publishes a destroy event to NATS."""
        settings = _make_settings(session_id="sess-destroy")
        agent = SandboxAgent(settings)

        mock_nc = AsyncMock()
        mock_nc.is_closed = False
        mock_nc.publish = AsyncMock()
        mock_nc.drain = AsyncMock()
        mock_nc.close = AsyncMock()
        agent._nc = mock_nc
        agent._health_server = MagicMock()

        await agent.stop()

        # Find the destroy event publish call
        calls = mock_nc.publish.call_args_list
        destroy_calls = [
            c for c in calls
            if c[0][0] == "sandbox.sess-destroy.health"
        ]
        assert len(destroy_calls) == 1
        data = json.loads(destroy_calls[0][0][1])
        assert data["type"] == "destroyed"
        assert data["session_id"] == "sess-destroy"

    @pytest.mark.asyncio
    async def test_stop_drains_and_closes_nats(self) -> None:
        """Test stop() drains and closes the NATS connection."""
        agent = SandboxAgent(_make_settings(session_id=""))
        mock_nc = AsyncMock()
        mock_nc.is_closed = False
        mock_nc.drain = AsyncMock()
        mock_nc.close = AsyncMock()
        agent._nc = mock_nc
        agent._health_server = MagicMock()

        await agent.stop()

        mock_nc.drain.assert_awaited_once()
        mock_nc.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_unsubscribes_all(self) -> None:
        """Test stop() unsubscribes from all NATS subscriptions."""
        agent = SandboxAgent(_make_settings(session_id=""))
        agent._nc = None
        agent._health_server = None

        mock_sub1 = AsyncMock()
        mock_sub2 = AsyncMock()
        agent._subscriptions = [mock_sub1, mock_sub2]

        await agent.stop()

        mock_sub1.unsubscribe.assert_awaited_once()
        mock_sub2.unsubscribe.assert_awaited_once()
        assert agent._subscriptions == []

    @pytest.mark.asyncio
    async def test_stop_shuts_down_agent_runner(self) -> None:
        """Test stop() calls agent runner shutdown."""
        agent = SandboxAgent(_make_settings(session_id=""))
        agent._nc = None
        agent._health_server = None

        mock_runner = AsyncMock()
        agent._agent_runner = mock_runner

        await agent.stop()

        mock_runner.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_stops_health_server(self) -> None:
        """Test stop() stops the health server."""
        agent = SandboxAgent(_make_settings(session_id=""))
        agent._nc = None
        mock_hs = MagicMock()
        agent._health_server = mock_hs

        await agent.stop()

        mock_hs.set_ready.assert_called_with(False)
        mock_hs.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_retry_tasks(self) -> None:
        """Test stop() cancels background retry tasks."""
        import asyncio

        agent = SandboxAgent(_make_settings(session_id=""))
        agent._nc = None
        agent._health_server = None

        async def forever() -> None:
            while True:
                await asyncio.sleep(100)

        agent._retry_tasks = [asyncio.create_task(forever())]
        await agent.stop()

        assert all(t.cancelled() or t.done() for t in agent._retry_tasks)

    @pytest.mark.asyncio
    async def test_stop_handles_nats_already_closed(self) -> None:
        """Test stop() is safe when NATS is already closed."""
        agent = SandboxAgent(_make_settings(session_id=""))
        mock_nc = MagicMock()
        mock_nc.is_closed = True
        agent._nc = mock_nc
        agent._health_server = None

        # Should not raise
        await agent.stop()


# ── Run Loop ──────────────────────────────────────────────────


class TestSandboxAgentRun:
    """Tests for the main run loop."""

    @pytest.mark.asyncio
    async def test_run_exits_when_shutdown_event_set(self) -> None:
        """Test run() exits when shutdown event is set."""
        import asyncio

        agent = SandboxAgent(_make_settings())
        agent._running = True

        async def stop_soon() -> None:
            await asyncio.sleep(0.05)
            agent._running = False
            agent._shutdown_event.set()

        asyncio.create_task(stop_soon())
        # Should return after shutdown event is set
        await asyncio.wait_for(agent.run(), timeout=2.0)
