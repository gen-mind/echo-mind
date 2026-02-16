"""Tests for MCP Gateway main module (MCPGateway class)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gateway.main import MCPGateway


class TestMCPGatewayInit:
    """Tests for MCPGateway initialization."""

    def test_init_defaults(self) -> None:
        """MCPGateway initializes with correct default state."""
        gateway = MCPGateway()

        assert gateway._health_server is None
        assert gateway._qdrant_connected is False
        assert gateway._embedder_connected is False
        assert gateway._db_connected is False
        assert gateway._nats_connected is False
        assert gateway._retry_tasks == []
        assert gateway._mcp_task is None
        assert gateway._db_engine is None
        assert gateway._clients is not None

    def test_init_loads_settings(self) -> None:
        """MCPGateway loads settings on init."""
        gateway = MCPGateway()
        assert gateway._settings is not None
        assert gateway._settings.enabled is True


class TestMCPGatewayReadiness:
    """Tests for readiness logic."""

    def test_not_ready_by_default(self) -> None:
        """Gateway is not ready when no connections are established."""
        gateway = MCPGateway()
        assert gateway._is_ready() is False

    def test_ready_when_all_connected(self) -> None:
        """Gateway is ready when all connections are established."""
        gateway = MCPGateway()
        gateway._qdrant_connected = True
        gateway._embedder_connected = True
        gateway._db_connected = True
        gateway._nats_connected = True
        assert gateway._is_ready() is True

    def test_not_ready_when_only_qdrant(self) -> None:
        """Gateway not ready with only Qdrant connected."""
        gateway = MCPGateway()
        gateway._qdrant_connected = True
        gateway._embedder_connected = False
        assert gateway._is_ready() is False

    def test_not_ready_when_only_embedder(self) -> None:
        """Gateway not ready with only Embedder connected."""
        gateway = MCPGateway()
        gateway._qdrant_connected = False
        gateway._embedder_connected = True
        assert gateway._is_ready() is False

    def test_update_readiness_sets_health_server(self) -> None:
        """_update_readiness calls health server set_ready."""
        gateway = MCPGateway()
        mock_health = MagicMock()
        gateway._health_server = mock_health

        gateway._qdrant_connected = True
        gateway._embedder_connected = True
        gateway._db_connected = True
        gateway._nats_connected = True
        gateway._update_readiness()

        mock_health.set_ready.assert_called_once_with(True)

    def test_update_readiness_no_health_server(self) -> None:
        """_update_readiness is a no-op when health server is None."""
        gateway = MCPGateway()
        gateway._health_server = None
        # Should not raise
        gateway._update_readiness()


class TestMCPGatewayStart:
    """Tests for the start method."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.register_api_proxy_tools")
    @patch("mcp_gateway.main.register_connector_tools")
    @patch("mcp_gateway.main.register_skills_tools")
    @patch("mcp_gateway.main.register_search_tools")
    @patch("mcp_gateway.main.AuditLoggingMiddleware")
    @patch("mcp_gateway.main.FastMCP")
    @patch("mcp_gateway.main.ApiKeyManager")
    @patch("mcp_gateway.main.ConnectorBackend")
    @patch("mcp_gateway.main.SkillExecutor")
    @patch("mcp_gateway.main.SkillRegistry")
    @patch("mcp_gateway.main.SearchBackend")
    @patch("mcp_gateway.main.NatsBackend")
    @patch("mcp_gateway.main.create_async_engine")
    @patch("mcp_gateway.main.EmbedderClient")
    @patch("mcp_gateway.main.QdrantDB")
    @patch("mcp_gateway.main.HealthServer")
    async def test_start_all_connections_succeed(
        self,
        mock_health_server_cls: MagicMock,
        mock_qdrant_cls: MagicMock,
        mock_embedder_cls: MagicMock,
        mock_engine_cls: MagicMock,
        mock_nats_cls: MagicMock,
        mock_search_backend_cls: MagicMock,
        mock_skill_registry_cls: MagicMock,
        mock_skill_executor_cls: MagicMock,
        mock_connector_backend_cls: MagicMock,
        mock_api_key_manager_cls: MagicMock,
        mock_fastmcp_cls: MagicMock,
        mock_audit_middleware_cls: MagicMock,
        mock_register_search: MagicMock,
        mock_register_skills: MagicMock,
        mock_register_connectors: MagicMock,
        mock_register_api_proxy: MagicMock,
    ) -> None:
        """Start succeeds when all connections are healthy."""
        # Setup mocks
        mock_health = MagicMock()
        mock_health_server_cls.return_value = mock_health

        mock_qdrant = AsyncMock()
        mock_qdrant_cls.return_value = mock_qdrant

        mock_embedder = AsyncMock()
        mock_embedder.health_check.return_value = True
        mock_embedder_cls.return_value = mock_embedder

        # DB engine mock — create_async_engine returns a sync object
        # with .connect() returning an async context manager
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_ctx.__aexit__.return_value = False
        mock_engine.connect.return_value = mock_ctx
        mock_engine.dispose = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        # NATS mock
        mock_nats = AsyncMock()
        mock_nats_cls.return_value = mock_nats

        mock_registry = MagicMock()
        mock_registry.skill_count = 3
        mock_skill_registry_cls.return_value = mock_registry

        mock_mcp = MagicMock()
        mock_mcp.run_http_async = AsyncMock()
        mock_fastmcp_cls.return_value = mock_mcp

        gateway = MCPGateway()
        await gateway.start()

        # Verify connections
        assert gateway._qdrant_connected is True
        assert gateway._embedder_connected is True
        assert gateway._db_connected is True
        assert gateway._nats_connected is True

        # Verify Qdrant init
        mock_qdrant.init.assert_awaited_once()

        # Verify Embedder health check
        mock_embedder.health_check.assert_awaited_once()

        # Verify skill registry loaded
        mock_registry.load.assert_called_once()

        # Verify MCP tools registered
        mock_register_search.assert_called_once()
        mock_register_skills.assert_called_once()
        mock_register_connectors.assert_called_once()
        mock_register_api_proxy.assert_called_once()

        # Verify health server readiness
        mock_health.set_ready.assert_called_with(True)

        # Cleanup
        await gateway.stop()

    @pytest.mark.asyncio
    async def test_start_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Start returns early when gateway is disabled."""
        monkeypatch.setenv("MCP_GATEWAY_ENABLED", "false")

        gateway = MCPGateway()
        await gateway.start()

        assert gateway._health_server is None

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.register_api_proxy_tools")
    @patch("mcp_gateway.main.register_connector_tools")
    @patch("mcp_gateway.main.register_skills_tools")
    @patch("mcp_gateway.main.register_search_tools")
    @patch("mcp_gateway.main.AuditLoggingMiddleware")
    @patch("mcp_gateway.main.FastMCP")
    @patch("mcp_gateway.main.ApiKeyManager")
    @patch("mcp_gateway.main.ConnectorBackend")
    @patch("mcp_gateway.main.SkillExecutor")
    @patch("mcp_gateway.main.SkillRegistry")
    @patch("mcp_gateway.main.SearchBackend")
    @patch("mcp_gateway.main.NatsBackend")
    @patch("mcp_gateway.main.create_async_engine")
    @patch("mcp_gateway.main.EmbedderClient")
    @patch("mcp_gateway.main.QdrantDB")
    @patch("mcp_gateway.main.HealthServer")
    async def test_start_qdrant_failure_triggers_retry(
        self,
        mock_health_server_cls: MagicMock,
        mock_qdrant_cls: MagicMock,
        mock_embedder_cls: MagicMock,
        mock_engine_cls: MagicMock,
        mock_nats_cls: MagicMock,
        mock_search_backend_cls: MagicMock,
        mock_skill_registry_cls: MagicMock,
        mock_skill_executor_cls: MagicMock,
        mock_connector_backend_cls: MagicMock,
        mock_api_key_manager_cls: MagicMock,
        mock_fastmcp_cls: MagicMock,
        mock_audit_middleware_cls: MagicMock,
        mock_register_search: MagicMock,
        mock_register_skills: MagicMock,
        mock_register_connectors: MagicMock,
        mock_register_api_proxy: MagicMock,
    ) -> None:
        """When Qdrant fails to connect, a retry task is spawned."""
        mock_health = MagicMock()
        mock_health_server_cls.return_value = mock_health

        mock_qdrant = AsyncMock()
        mock_qdrant.init.side_effect = ConnectionError("Qdrant down")
        mock_qdrant_cls.return_value = mock_qdrant

        mock_embedder = AsyncMock()
        mock_embedder.health_check.return_value = True
        mock_embedder_cls.return_value = mock_embedder

        # DB engine mock
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine_cls.return_value = mock_engine

        # NATS mock
        mock_nats = AsyncMock()
        mock_nats_cls.return_value = mock_nats

        mock_registry = MagicMock()
        mock_registry.skill_count = 0
        mock_skill_registry_cls.return_value = mock_registry

        mock_mcp = MagicMock()
        mock_mcp.run_http_async = AsyncMock()
        mock_fastmcp_cls.return_value = mock_mcp

        gateway = MCPGateway()
        await gateway.start()

        assert gateway._qdrant_connected is False
        assert gateway._embedder_connected is True

        # Not ready because Qdrant is down
        mock_health.set_ready.assert_called_with(False)

        await gateway.stop()

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.register_api_proxy_tools")
    @patch("mcp_gateway.main.register_connector_tools")
    @patch("mcp_gateway.main.register_skills_tools")
    @patch("mcp_gateway.main.register_search_tools")
    @patch("mcp_gateway.main.AuditLoggingMiddleware")
    @patch("mcp_gateway.main.FastMCP")
    @patch("mcp_gateway.main.ApiKeyManager")
    @patch("mcp_gateway.main.ConnectorBackend")
    @patch("mcp_gateway.main.SkillExecutor")
    @patch("mcp_gateway.main.SkillRegistry")
    @patch("mcp_gateway.main.SearchBackend")
    @patch("mcp_gateway.main.NatsBackend")
    @patch("mcp_gateway.main.create_async_engine")
    @patch("mcp_gateway.main.EmbedderClient")
    @patch("mcp_gateway.main.QdrantDB")
    @patch("mcp_gateway.main.HealthServer")
    async def test_start_embedder_failure_triggers_retry(
        self,
        mock_health_server_cls: MagicMock,
        mock_qdrant_cls: MagicMock,
        mock_embedder_cls: MagicMock,
        mock_engine_cls: MagicMock,
        mock_nats_cls: MagicMock,
        mock_search_backend_cls: MagicMock,
        mock_skill_registry_cls: MagicMock,
        mock_skill_executor_cls: MagicMock,
        mock_connector_backend_cls: MagicMock,
        mock_api_key_manager_cls: MagicMock,
        mock_fastmcp_cls: MagicMock,
        mock_audit_middleware_cls: MagicMock,
        mock_register_search: MagicMock,
        mock_register_skills: MagicMock,
        mock_register_connectors: MagicMock,
        mock_register_api_proxy: MagicMock,
    ) -> None:
        """When Embedder health check fails, a retry task is spawned."""
        mock_health = MagicMock()
        mock_health_server_cls.return_value = mock_health

        mock_qdrant = AsyncMock()
        mock_qdrant_cls.return_value = mock_qdrant

        mock_embedder = AsyncMock()
        mock_embedder.health_check.return_value = False
        mock_embedder_cls.return_value = mock_embedder

        # DB engine mock
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine_cls.return_value = mock_engine

        # NATS mock
        mock_nats = AsyncMock()
        mock_nats_cls.return_value = mock_nats

        mock_registry = MagicMock()
        mock_registry.skill_count = 0
        mock_skill_registry_cls.return_value = mock_registry

        mock_mcp = MagicMock()
        mock_mcp.run_http_async = AsyncMock()
        mock_fastmcp_cls.return_value = mock_mcp

        gateway = MCPGateway()
        await gateway.start()

        assert gateway._qdrant_connected is True
        assert gateway._embedder_connected is False

        # Not ready because Embedder is down
        mock_health.set_ready.assert_called_with(False)

        await gateway.stop()

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.register_api_proxy_tools")
    @patch("mcp_gateway.main.register_connector_tools")
    @patch("mcp_gateway.main.register_skills_tools")
    @patch("mcp_gateway.main.register_search_tools")
    @patch("mcp_gateway.main.AuditLoggingMiddleware")
    @patch("mcp_gateway.main.FastMCP")
    @patch("mcp_gateway.main.ApiKeyManager")
    @patch("mcp_gateway.main.ConnectorBackend")
    @patch("mcp_gateway.main.SkillExecutor")
    @patch("mcp_gateway.main.SkillRegistry")
    @patch("mcp_gateway.main.SearchBackend")
    @patch("mcp_gateway.main.NatsBackend")
    @patch("mcp_gateway.main.create_async_engine")
    @patch("mcp_gateway.main.EmbedderClient")
    @patch("mcp_gateway.main.QdrantDB")
    @patch("mcp_gateway.main.HealthServer")
    async def test_start_all_connections_fail(
        self,
        mock_health_server_cls: MagicMock,
        mock_qdrant_cls: MagicMock,
        mock_embedder_cls: MagicMock,
        mock_engine_cls: MagicMock,
        mock_nats_cls: MagicMock,
        mock_search_backend_cls: MagicMock,
        mock_skill_registry_cls: MagicMock,
        mock_skill_executor_cls: MagicMock,
        mock_connector_backend_cls: MagicMock,
        mock_api_key_manager_cls: MagicMock,
        mock_fastmcp_cls: MagicMock,
        mock_audit_middleware_cls: MagicMock,
        mock_register_search: MagicMock,
        mock_register_skills: MagicMock,
        mock_register_connectors: MagicMock,
        mock_register_api_proxy: MagicMock,
    ) -> None:
        """Service still starts when all connections fail (degraded mode)."""
        mock_health = MagicMock()
        mock_health_server_cls.return_value = mock_health

        mock_qdrant = AsyncMock()
        mock_qdrant.init.side_effect = ConnectionError("Qdrant down")
        mock_qdrant_cls.return_value = mock_qdrant

        mock_embedder = AsyncMock()
        mock_embedder.health_check.side_effect = Exception("Embedder unreachable")
        mock_embedder_cls.return_value = mock_embedder

        # DB engine fails
        mock_engine_cls.side_effect = Exception("DB unreachable")

        # NATS fails
        mock_nats = AsyncMock()
        mock_nats.connect.side_effect = Exception("NATS unreachable")
        mock_nats_cls.return_value = mock_nats

        mock_registry = MagicMock()
        mock_registry.skill_count = 0
        mock_skill_registry_cls.return_value = mock_registry

        mock_mcp = MagicMock()
        mock_mcp.run_http_async = AsyncMock()
        mock_fastmcp_cls.return_value = mock_mcp

        gateway = MCPGateway()
        await gateway.start()

        assert gateway._qdrant_connected is False
        assert gateway._embedder_connected is False
        assert gateway._db_connected is False
        assert gateway._nats_connected is False
        assert len(gateway._retry_tasks) == 4

        await gateway.stop()


class TestMCPGatewayStop:
    """Tests for the stop method."""

    @pytest.mark.asyncio
    async def test_stop_sets_not_ready(self) -> None:
        """Stop marks health server as not ready."""
        gateway = MCPGateway()
        mock_health = MagicMock()
        gateway._health_server = mock_health

        await gateway.stop()

        mock_health.set_ready.assert_called_with(False)

    @pytest.mark.asyncio
    async def test_stop_cancels_retry_tasks(self) -> None:
        """Stop cancels all pending retry tasks."""
        gateway = MCPGateway()

        async def _noop() -> None:
            await asyncio.sleep(999999)

        task1 = asyncio.create_task(_noop())
        task2 = asyncio.create_task(_noop())
        gateway._retry_tasks = [task1, task2]

        await gateway.stop()

        assert task1.cancelled()
        assert task2.cancelled()

    @pytest.mark.asyncio
    async def test_stop_cancels_mcp_task(self) -> None:
        """Stop cancels the MCP server task."""
        gateway = MCPGateway()

        async def _block_forever() -> None:
            await asyncio.sleep(999999)

        gateway._mcp_task = asyncio.create_task(_block_forever())
        await gateway.stop()

        assert gateway._mcp_task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_closes_qdrant(self) -> None:
        """Stop closes the Qdrant connection."""
        gateway = MCPGateway()

        mock_qdrant = AsyncMock()
        gateway._clients.qdrant = mock_qdrant

        await gateway.stop()

        mock_qdrant.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_closes_embedder(self) -> None:
        """Stop closes the Embedder connection."""
        gateway = MCPGateway()

        mock_embedder = AsyncMock()
        gateway._clients.embedder = mock_embedder

        await gateway.stop()

        mock_embedder.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_no_connections(self) -> None:
        """Stop handles case where no connections were established."""
        gateway = MCPGateway()
        # Should not raise
        await gateway.stop()


class TestMCPGatewayRetry:
    """Tests for background retry logic."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.QdrantDB")
    async def test_retry_qdrant_succeeds(
        self, mock_qdrant_cls: MagicMock
    ) -> None:
        """Qdrant retry task succeeds on reconnection."""
        mock_qdrant = AsyncMock()
        mock_qdrant_cls.return_value = mock_qdrant

        gateway = MCPGateway()
        mock_health = MagicMock()
        gateway._health_server = mock_health
        gateway._embedder_connected = True
        gateway._db_connected = True
        gateway._nats_connected = True
        gateway._qdrant_connected = False

        # Await directly — mocked sleep returns instantly, init succeeds,
        # loop terminates because _qdrant_connected becomes True.
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await gateway._retry_qdrant_connection()

        assert gateway._qdrant_connected is True
        mock_health.set_ready.assert_called_with(True)

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.EmbedderClient")
    async def test_retry_embedder_succeeds(
        self, mock_embedder_cls: MagicMock
    ) -> None:
        """Embedder retry task succeeds on reconnection."""
        mock_embedder = AsyncMock()
        mock_embedder.health_check.return_value = True
        mock_embedder_cls.return_value = mock_embedder

        gateway = MCPGateway()
        mock_health = MagicMock()
        gateway._health_server = mock_health
        gateway._qdrant_connected = True
        gateway._db_connected = True
        gateway._nats_connected = True
        gateway._embedder_connected = False

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await gateway._retry_embedder_connection()

        assert gateway._embedder_connected is True
        mock_health.set_ready.assert_called_with(True)

    @pytest.mark.asyncio
    @patch("mcp_gateway.main.QdrantDB")
    async def test_retry_qdrant_continues_on_failure(
        self, mock_qdrant_cls: MagicMock
    ) -> None:
        """Qdrant retry continues when reconnection fails, then succeeds."""
        mock_qdrant = AsyncMock()
        # Fail twice, then succeed
        mock_qdrant.init.side_effect = [
            ConnectionError("still down"),
            ConnectionError("still down"),
            None,
        ]
        mock_qdrant_cls.return_value = mock_qdrant

        gateway = MCPGateway()
        mock_health = MagicMock()
        gateway._health_server = mock_health
        gateway._qdrant_connected = False

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await gateway._retry_qdrant_connection()

        assert gateway._qdrant_connected is True
        # Sleep called 3 times (once per iteration: 2 failures + 1 success)
        assert mock_sleep.await_count == 3
