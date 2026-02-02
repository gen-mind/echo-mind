"""Unit tests for orchestrator service logic."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from echomind_lib.models.internal import orchestrator_pb2
from echomind_lib.models.public import connector_pb2
from orchestrator.logic.orchestrator_service import (
    CONNECTOR_SUBJECTS,
    CONNECTOR_TYPE_MAP,
    CONNECTOR_SCOPE_MAP,
    OrchestratorService,
)
from orchestrator.logic.exceptions import (
    ConnectorNotFoundError,
    SyncTriggerError,
)


def create_mock_connector(
    id: int = 1,
    type: str = "web",
    user_id: int = 1,
    scope: str = "user",
    scope_id: str | None = None,
    config: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    status: str = "active",
    status_message: str | None = None,
) -> MagicMock:
    """Create a mock connector for testing."""
    connector = MagicMock()
    connector.id = id
    connector.type = type
    connector.user_id = user_id
    connector.scope = scope
    connector.scope_id = scope_id
    connector.config = config or {"url": "https://example.com"}
    connector.state = state or {}
    connector.status = status
    connector.status_message = status_message
    return connector


class TestConnectorSubjects:
    """Tests for NATS subject mapping."""

    def test_web_subject(self) -> None:
        """Test web connector subject mapping."""
        assert CONNECTOR_SUBJECTS["web"] == "connector.sync.web"

    def test_file_subject(self) -> None:
        """Test file connector subject mapping."""
        assert CONNECTOR_SUBJECTS["file"] == "connector.sync.file"

    def test_onedrive_subject(self) -> None:
        """Test OneDrive connector subject mapping."""
        assert CONNECTOR_SUBJECTS["onedrive"] == "connector.sync.onedrive"

    def test_google_drive_subject(self) -> None:
        """Test Google Drive connector subject mapping."""
        assert CONNECTOR_SUBJECTS["google_drive"] == "connector.sync.google_drive"

    def test_teams_subject(self) -> None:
        """Test Teams connector subject mapping."""
        assert CONNECTOR_SUBJECTS["teams"] == "connector.sync.teams"


class TestConnectorMappings:
    """Tests for connector type and scope mappings."""

    def test_type_map_matches_subjects(self) -> None:
        """Verify type map has same keys as subject map."""
        assert set(CONNECTOR_TYPE_MAP.keys()) == set(CONNECTOR_SUBJECTS.keys())

    def test_type_map_values_are_valid_enums(self) -> None:
        """Verify all type map values are valid ConnectorType enums."""
        for type_name, enum_value in CONNECTOR_TYPE_MAP.items():
            assert enum_value != connector_pb2.ConnectorType.CONNECTOR_TYPE_UNSPECIFIED, \
                f"Type {type_name} should not map to UNSPECIFIED"

    def test_scope_map_has_team_alias(self) -> None:
        """Verify 'team' maps to GROUP (critical for data integrity)."""
        assert "team" in CONNECTOR_SCOPE_MAP
        assert CONNECTOR_SCOPE_MAP["team"] == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP

    def test_scope_map_team_equals_group(self) -> None:
        """Verify 'team' and 'group' map to same enum value."""
        assert CONNECTOR_SCOPE_MAP["team"] == CONNECTOR_SCOPE_MAP["group"]

    def test_scope_map_all_values(self) -> None:
        """Verify all expected scopes are mapped."""
        assert CONNECTOR_SCOPE_MAP["user"] == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_USER
        assert CONNECTOR_SCOPE_MAP["group"] == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP
        assert CONNECTOR_SCOPE_MAP["org"] == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_ORG


class TestOrchestratorService:
    """Tests for OrchestratorService class."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_publisher(self) -> AsyncMock:
        """Create mock NATS publisher."""
        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        return publisher

    @pytest.fixture
    def service(
        self,
        mock_session: AsyncMock,
        mock_publisher: AsyncMock,
    ) -> OrchestratorService:
        """Create orchestrator service with mocks."""
        return OrchestratorService(mock_session, mock_publisher)

    @pytest.mark.asyncio
    async def test_check_and_trigger_syncs_no_connectors(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync check with no connectors due."""
        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_due_for_sync = AsyncMock(return_value=[])

            triggered = await service.check_and_trigger_syncs()

            assert triggered == 0
            mock_crud.get_due_for_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_and_trigger_syncs_with_connectors(
        self,
        service: OrchestratorService,
        mock_publisher: AsyncMock,
    ) -> None:
        """Test sync check triggers syncs for due connectors."""
        connectors = [
            create_mock_connector(id=1, type="web"),
            create_mock_connector(id=2, type="onedrive"),
        ]

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_due_for_sync = AsyncMock(return_value=connectors)
            mock_crud.update_status = AsyncMock(return_value=connectors[0])

            triggered = await service.check_and_trigger_syncs()

            assert triggered == 2
            assert mock_publisher.publish.call_count == 2

    @pytest.mark.asyncio
    async def test_check_and_trigger_syncs_handles_errors(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync check handles errors gracefully."""
        connector = create_mock_connector(id=1, type="web")

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_due_for_sync = AsyncMock(return_value=[connector])
            mock_crud.update_status = AsyncMock(return_value=None)  # Simulate failure

            triggered = await service.check_and_trigger_syncs()

            assert triggered == 0

    @pytest.mark.asyncio
    async def test_trigger_sync_publishes_protobuf_message(
        self,
        service: OrchestratorService,
        mock_publisher: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test that trigger sync publishes Protobuf-serialized NATS message."""
        connector = create_mock_connector(id=1, type="web", user_id=10)

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.update_status = AsyncMock(return_value=connector)

            await service._trigger_sync(connector)

            mock_publisher.publish.assert_called_once()
            call_args = mock_publisher.publish.call_args
            assert call_args.kwargs["subject"] == "connector.sync.web"

            # Verify payload is valid Protobuf, not JSON
            payload = call_args.kwargs["payload"]
            request = orchestrator_pb2.ConnectorSyncRequest()
            request.ParseFromString(payload)  # Should not raise

            assert request.connector_id == 1
            assert request.user_id == 10
            assert request.type == connector_pb2.ConnectorType.CONNECTOR_TYPE_WEB
            assert len(request.chunking_session) > 0

    @pytest.mark.asyncio
    async def test_trigger_sync_unknown_type_raises(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that unknown connector type raises error."""
        connector = create_mock_connector(id=1, type="unknown_type")

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.update_status = AsyncMock(return_value=connector)

            with pytest.raises(SyncTriggerError) as exc_info:
                await service._trigger_sync(connector)

            assert "Unknown connector type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_trigger_sync_nats_failure_raises(
        self,
        service: OrchestratorService,
        mock_publisher: AsyncMock,
    ) -> None:
        """Test that NATS publish failure raises error."""
        connector = create_mock_connector(id=1, type="web")
        mock_publisher.publish.side_effect = Exception("NATS error")

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.update_status = AsyncMock(return_value=connector)

            with pytest.raises(SyncTriggerError) as exc_info:
                await service._trigger_sync(connector)

            assert "NATS publish failed" in str(exc_info.value)

    def test_build_sync_request(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync request Protobuf building."""
        connector = create_mock_connector(
            id=1,
            type="web",
            user_id=10,
            scope="user",
            scope_id=None,
            config={"url": "https://example.com"},
            state={"etag": "abc123"},
        )
        session_id = "test-session-123"

        request = service._build_sync_request(connector, session_id)

        assert request.connector_id == 1
        assert request.user_id == 10
        assert request.type == connector_pb2.ConnectorType.CONNECTOR_TYPE_WEB
        assert request.scope == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_USER
        assert request.chunking_session == session_id

        # Verify config was serialized
        config_dict = dict(request.config)
        assert config_dict.get("url") == "https://example.com"

        # Verify state was serialized
        state_dict = dict(request.state)
        assert state_dict.get("etag") == "abc123"

    def test_build_sync_request_with_scope_id(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync request includes scope_id when present."""
        connector = create_mock_connector(
            id=2,
            type="google_drive",
            user_id=20,
            scope="group",
            scope_id="engineering-team",
        )
        session_id = "test-session-456"

        request = service._build_sync_request(connector, session_id)

        assert request.connector_id == 2
        assert request.scope == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP
        assert request.scope_id == "engineering-team"
        assert request.type == connector_pb2.ConnectorType.CONNECTOR_TYPE_GOOGLE_DRIVE

    def test_build_sync_request_all_connector_types(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync request handles all connector types correctly."""
        type_mapping = {
            "web": connector_pb2.ConnectorType.CONNECTOR_TYPE_WEB,
            "file": connector_pb2.ConnectorType.CONNECTOR_TYPE_FILE,
            "onedrive": connector_pb2.ConnectorType.CONNECTOR_TYPE_ONEDRIVE,
            "google_drive": connector_pb2.ConnectorType.CONNECTOR_TYPE_GOOGLE_DRIVE,
            "teams": connector_pb2.ConnectorType.CONNECTOR_TYPE_TEAMS,
        }

        for type_str, expected_enum in type_mapping.items():
            connector = create_mock_connector(id=1, type=type_str)
            request = service._build_sync_request(connector, "session-123")
            assert request.type == expected_enum, f"Failed for type: {type_str}"

    def test_build_sync_request_all_scope_types(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync request handles all scope types correctly."""
        scope_mapping = {
            "user": connector_pb2.ConnectorScope.CONNECTOR_SCOPE_USER,
            "group": connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP,
            "team": connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP,  # team -> GROUP
            "org": connector_pb2.ConnectorScope.CONNECTOR_SCOPE_ORG,
        }

        for scope_str, expected_enum in scope_mapping.items():
            connector = create_mock_connector(id=1, type="web", scope=scope_str)
            request = service._build_sync_request(connector, "session-123")
            assert request.scope == expected_enum, f"Failed for scope: {scope_str}"

    def test_build_sync_request_team_scope_maps_to_group(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that 'team' scope correctly maps to CONNECTOR_SCOPE_GROUP.

        This is critical: the database stores 'team' but proto only has GROUP.
        Silent fallback to USER would corrupt data.
        """
        connector = create_mock_connector(
            id=1,
            type="web",
            scope="team",  # Database value
            scope_id="sales-team",
        )

        request = service._build_sync_request(connector, "session-123")

        # Must map to GROUP, not USER or anything else
        assert request.scope == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP
        assert request.scope_id == "sales-team"

    def test_build_sync_request_invalid_type_raises(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that unknown connector type raises error, not silent fallback."""
        connector = create_mock_connector(id=1, type="invalid_type")

        with pytest.raises(SyncTriggerError) as exc_info:
            service._build_sync_request(connector, "session-123")

        assert "Unknown connector type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_not_found(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test manual sync with non-existent connector."""
        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=None)

            with pytest.raises(ConnectorNotFoundError) as exc_info:
                await service.trigger_manual_sync(999)

            assert exc_info.value.connector_id == 999

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_already_pending(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test manual sync on already pending connector."""
        connector = create_mock_connector(id=1, status="pending")

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=connector)

            with pytest.raises(SyncTriggerError) as exc_info:
                await service.trigger_manual_sync(1)

            assert "already pending" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_disabled(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test manual sync on disabled connector."""
        connector = create_mock_connector(id=1, status="disabled")

        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=connector)

            with pytest.raises(SyncTriggerError) as exc_info:
                await service.trigger_manual_sync(1)

            assert "disabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_sync_stats(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test sync statistics retrieval."""
        with patch(
            "orchestrator.logic.orchestrator_service.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_status = AsyncMock(
                side_effect=lambda s, status: [MagicMock()] * (1 if status == "active" else 0)
            )
            mock_crud.get_due_for_sync = AsyncMock(return_value=[MagicMock()])

            stats = await service.get_sync_stats()

            assert stats["active"] == 1
            assert stats["pending"] == 0
            assert stats["due_for_sync"] == 1


class TestProtobufCompatibility:
    """Tests for Protobuf message compatibility with Connector service."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_publisher(self) -> AsyncMock:
        """Create mock NATS publisher."""
        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        return publisher

    @pytest.fixture
    def service(
        self,
        mock_session: AsyncMock,
        mock_publisher: AsyncMock,
    ) -> OrchestratorService:
        """Create orchestrator service with mocks."""
        return OrchestratorService(mock_session, mock_publisher)

    def test_serialized_message_parseable_by_connector(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that serialized message can be parsed exactly like Connector does.

        This test mimics connector/main.py:336-337:
            request = ConnectorSyncRequest()
            request.ParseFromString(msg.data)
        """
        connector = create_mock_connector(
            id=42,
            type="google_drive",
            user_id=123,
            scope="group",
            scope_id="sales-team",
            config={"folder_id": "abc123", "include_subfolders": True},
            state={"page_token": "xyz789"},
        )
        chunking_session = "test-session-uuid"

        # Build and serialize (what Orchestrator does)
        request = service._build_sync_request(connector, chunking_session)
        serialized = request.SerializeToString()

        # Parse (what Connector does - exactly like connector/main.py:336-337)
        parsed = orchestrator_pb2.ConnectorSyncRequest()
        parsed.ParseFromString(serialized)

        # Verify all fields are correctly transmitted
        assert parsed.connector_id == 42
        assert parsed.user_id == 123
        assert parsed.type == connector_pb2.ConnectorType.CONNECTOR_TYPE_GOOGLE_DRIVE
        assert parsed.scope == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP
        assert parsed.scope_id == "sales-team"
        assert parsed.chunking_session == chunking_session

        # Verify config struct
        config = dict(parsed.config)
        assert config.get("folder_id") == "abc123"
        assert config.get("include_subfolders") is True

        # Verify state struct
        state = dict(parsed.state)
        assert state.get("page_token") == "xyz789"

    def test_serialized_message_with_team_scope(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that 'team' scope is correctly serialized as GROUP.

        Critical test: ensures team-scoped connectors work end-to-end.
        """
        connector = create_mock_connector(
            id=99,
            type="onedrive",
            user_id=456,
            scope="team",  # Database stores 'team'
            scope_id="engineering",
        )

        # Build and serialize
        request = service._build_sync_request(connector, "session-abc")
        serialized = request.SerializeToString()

        # Parse like Connector does
        parsed = orchestrator_pb2.ConnectorSyncRequest()
        parsed.ParseFromString(serialized)

        # Must be GROUP, not TEAM (which doesn't exist) or USER (wrong)
        assert parsed.scope == connector_pb2.ConnectorScope.CONNECTOR_SCOPE_GROUP
        assert parsed.scope_id == "engineering"

    def test_empty_config_and_state_handled(
        self,
        service: OrchestratorService,
    ) -> None:
        """Test that empty config/state don't cause issues."""
        connector = create_mock_connector(
            id=1,
            type="web",
            config=None,
            state=None,
        )
        # Override the mock to return None
        connector.config = None
        connector.state = None

        request = service._build_sync_request(connector, "session-123")
        serialized = request.SerializeToString()

        # Should not raise when parsing
        parsed = orchestrator_pb2.ConnectorSyncRequest()
        parsed.ParseFromString(serialized)

        assert parsed.connector_id == 1
        # Empty structs are valid
        assert len(dict(parsed.config)) == 0
        assert len(dict(parsed.state)) == 0
