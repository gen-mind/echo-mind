"""
Unit tests for ConnectorService.

Tests connector CRUD operations and NATS sync message publishing.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.logic.connector_service import ConnectorService
from api.logic.exceptions import NotFoundError


class TestConnectorService:
    """Tests for ConnectorService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def mock_nats(self):
        """Create a mock NATS publisher."""
        nats = AsyncMock()
        nats.publish = AsyncMock()
        return nats

    @pytest.fixture
    def mock_connector(self):
        """Create a mock connector ORM object."""
        connector = MagicMock()
        connector.id = 1
        connector.name = "Test Connector"
        connector.type = "google_drive"
        connector.user_id = 42
        connector.scope = "user"
        connector.scope_id = ""
        connector.config = {"folder_id": "abc123"}
        connector.state = {}
        connector.status = "active"
        connector.status_message = None
        connector.last_sync_at = None
        connector.docs_analyzed = 0
        connector.refresh_freq_minutes = 60
        connector.deleted_date = None
        return connector

    @pytest.fixture
    def service(self, mock_db, mock_nats):
        """Create a ConnectorService with mocked dependencies."""
        return ConnectorService(mock_db, mock_nats)

    @pytest.fixture
    def service_no_nats(self, mock_db):
        """Create a ConnectorService without NATS."""
        return ConnectorService(mock_db, None)

    # =========================================================================
    # get_connector tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_connector_success(self, service, mock_db, mock_connector):
        """Test getting an existing connector."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        result = await service.get_connector(1, 42)

        assert result == mock_connector
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connector_not_found(self, service, mock_db):
        """Test getting a non-existent connector raises NotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError) as exc_info:
            await service.get_connector(999, 42)

        assert "Connector" in str(exc_info.value)
        assert "999" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_connector_wrong_user(self, service, mock_db):
        """Test getting a connector owned by different user raises NotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Query filters by user_id
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await service.get_connector(1, 999)  # Wrong user

    # =========================================================================
    # create_connector tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_connector_success(self, service, mock_db, mock_nats):
        """Test creating a connector successfully."""
        # Setup mock to return a connector with ID after flush
        def set_connector_id(connector):
            connector.id = 1
            connector.type = "google_drive"
            connector.user_id = 42
            connector.scope = "user"
            connector.scope_id = ""
            connector.config = {}
            connector.state = {}

        mock_db.refresh.side_effect = set_connector_id

        result = await service.create_connector(
            name="New Connector",
            connector_type="google_drive",
            user_id=42,
            config={"folder_id": "abc"},
            trigger_sync=True,
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()
        mock_nats.publish.assert_called_once()

        # Verify NATS subject
        call_args = mock_nats.publish.call_args
        assert call_args[0][0] == "connector.sync.google_drive"

    @pytest.mark.asyncio
    async def test_create_connector_without_sync(self, service, mock_db, mock_nats):
        """Test creating a connector without triggering sync."""
        def set_connector_id(connector):
            connector.id = 1
            connector.type = "google_drive"
            connector.user_id = 42
            connector.scope = None
            connector.scope_id = ""
            connector.config = {}
            connector.state = {}

        mock_db.refresh.side_effect = set_connector_id

        await service.create_connector(
            name="New Connector",
            connector_type="google_drive",
            user_id=42,
            trigger_sync=False,
        )

        mock_db.add.assert_called_once()
        mock_nats.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_connector_no_nats_available(self, service_no_nats, mock_db):
        """Test creating a connector when NATS is not available."""
        def set_connector_id(connector):
            connector.id = 1
            connector.type = "onedrive"
            connector.user_id = 42
            connector.scope = None
            connector.scope_id = ""
            connector.config = {}
            connector.state = {}

        mock_db.refresh.side_effect = set_connector_id

        # Should not raise even with trigger_sync=True
        result = await service_no_nats.create_connector(
            name="New Connector",
            connector_type="onedrive",
            user_id=42,
            trigger_sync=True,
        )

        mock_db.add.assert_called_once()

    # =========================================================================
    # update_connector tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_update_connector_success(self, service, mock_db, mock_connector):
        """Test updating a connector."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        result = await service.update_connector(
            connector_id=1,
            user_id=42,
            name="Updated Name",
            config={"new": "config"},
        )

        assert result.name == "Updated Name"
        assert result.config == {"new": "config"}

    @pytest.mark.asyncio
    async def test_update_connector_not_found(self, service, mock_db):
        """Test updating non-existent connector raises NotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await service.update_connector(
                connector_id=999,
                user_id=42,
                name="New Name",
            )

    @pytest.mark.asyncio
    async def test_update_connector_partial(self, service, mock_db, mock_connector):
        """Test partial update only changes specified fields."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        original_config = mock_connector.config.copy()

        result = await service.update_connector(
            connector_id=1,
            user_id=42,
            name="New Name Only",
            # config not provided - should not change
        )

        assert result.name == "New Name Only"
        assert result.config == original_config

    # =========================================================================
    # delete_connector tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_delete_connector_success(self, service, mock_db, mock_connector):
        """Test soft deleting a connector."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        await service.delete_connector(1, 42)

        assert mock_connector.deleted_date is not None
        assert isinstance(mock_connector.deleted_date, datetime)

    @pytest.mark.asyncio
    async def test_delete_connector_not_found(self, service, mock_db):
        """Test deleting non-existent connector raises NotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await service.delete_connector(999, 42)

    # =========================================================================
    # trigger_sync tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_trigger_sync_success(self, service, mock_db, mock_nats, mock_connector):
        """Test triggering a sync successfully."""
        mock_connector.status = "active"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        success, message = await service.trigger_sync(1, 42)

        assert success is True
        assert message == "Sync triggered"
        assert mock_connector.status == "pending"
        mock_nats.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_sync_already_syncing(self, service, mock_db, mock_nats, mock_connector):
        """Test triggering sync when already syncing returns failure."""
        mock_connector.status = "syncing"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        success, message = await service.trigger_sync(1, 42)

        assert success is False
        assert "already in progress" in message
        mock_nats.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_sync_no_nats(self, service_no_nats, mock_db, mock_connector):
        """Test triggering sync when NATS is not available."""
        mock_connector.status = "active"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connector
        mock_db.execute.return_value = mock_result

        success, message = await service_no_nats.trigger_sync(1, 42)

        assert success is False
        assert "NATS not available" in message

    @pytest.mark.asyncio
    async def test_trigger_sync_not_found(self, service, mock_db):
        """Test triggering sync for non-existent connector raises NotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await service.trigger_sync(999, 42)

    # =========================================================================
    # get_connector_status tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_connector_status_success(self, service, mock_db, mock_connector):
        """Test getting connector status."""
        mock_connector.status = "active"
        mock_connector.status_message = "Last sync successful"
        mock_connector.last_sync_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_connector.docs_analyzed = 100

        # First call returns connector, second returns count
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_connector

        mock_result2 = MagicMock()
        mock_result2.scalar.return_value = 5  # 5 pending docs

        mock_db.execute.side_effect = [mock_result1, mock_result2]

        result = await service.get_connector_status(1, 42)

        assert result["status"] == "active"
        assert result["status_message"] == "Last sync successful"
        assert result["docs_analyzed"] == 100
        assert result["docs_pending"] == 5

    # =========================================================================
    # _publish_sync_message tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_publish_sync_message_content(self, service, mock_db, mock_nats, mock_connector):
        """Test that sync message contains correct data."""
        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")

            await service._publish_sync_message(mock_connector)

        mock_nats.publish.assert_called_once()
        call_args = mock_nats.publish.call_args

        # Check subject
        subject = call_args[0][0]
        assert subject == "connector.sync.google_drive"

        # Check payload is bytes (serialized protobuf)
        payload = call_args[0][1]
        assert isinstance(payload, bytes)

    @pytest.mark.asyncio
    async def test_publish_sync_message_different_types(self, service, mock_nats):
        """Test sync message subject varies by connector type."""
        for connector_type, expected_subject in [
            ("google_drive", "connector.sync.google_drive"),
            ("onedrive", "connector.sync.onedrive"),
            ("teams", "connector.sync.teams"),
        ]:
            mock_nats.reset_mock()

            connector = MagicMock()
            connector.id = 1
            connector.type = connector_type
            connector.user_id = 42
            connector.scope = "user"
            connector.scope_id = ""
            connector.config = {}
            connector.state = {}

            await service._publish_sync_message(connector)

            call_args = mock_nats.publish.call_args
            assert call_args[0][0] == expected_subject


class TestConnectorServiceIntegration:
    """Integration-style tests for ConnectorService."""

    @pytest.mark.asyncio
    async def test_create_and_trigger_sync_workflow(self):
        """Test full workflow: create connector -> trigger sync."""
        mock_db = AsyncMock()
        mock_nats = AsyncMock()

        # Setup mocks
        def set_connector_id(connector):
            connector.id = 1
            connector.type = "google_drive"
            connector.user_id = 42
            connector.scope = "user"
            connector.scope_id = ""
            connector.config = {}
            connector.state = {}
            connector.status = "pending"

        mock_db.refresh.side_effect = set_connector_id
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        service = ConnectorService(mock_db, mock_nats)

        # Create connector (triggers initial sync)
        connector = await service.create_connector(
            name="Test",
            connector_type="google_drive",
            user_id=42,
            trigger_sync=True,
        )

        # Verify NATS was called during creation
        assert mock_nats.publish.call_count == 1

        # Setup for trigger_sync
        mock_result = MagicMock()
        connector_orm = MagicMock()
        connector_orm.id = 1
        connector_orm.type = "google_drive"
        connector_orm.user_id = 42
        connector_orm.scope = "user"
        connector_orm.scope_id = ""
        connector_orm.config = {}
        connector_orm.state = {}
        connector_orm.status = "active"  # Simulate it finished syncing
        mock_result.scalar_one_or_none.return_value = connector_orm
        mock_db.execute.return_value = mock_result

        # Manually trigger another sync
        success, message = await service.trigger_sync(1, 42)

        assert success is True
        assert mock_nats.publish.call_count == 2  # Initial + manual


# Run init file creation
@pytest.fixture(scope="module", autouse=True)
def create_init_files():
    """Create __init__.py files in test directories."""
    import os

    dirs = [
        "/Users/gp/Developer/EchoMind/tests/unit/api",
        "/Users/gp/Developer/EchoMind/tests/unit/api/logic",
    ]
    for d in dirs:
        init_file = os.path.join(d, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("")
