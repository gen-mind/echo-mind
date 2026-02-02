"""
Unit tests for ConnectorCRUD operations.

Tests for the upload connector management functionality.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from echomind_lib.db.crud.connector import ConnectorCRUD


class TestConnectorCRUDUploadConnector:
    """Tests for ConnectorCRUD upload connector methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def crud(self):
        """Create ConnectorCRUD instance."""
        return ConnectorCRUD()

    @pytest.fixture
    def mock_connector(self):
        """Create a mock connector."""
        connector = MagicMock()
        connector.id = 1
        connector.user_id = 42
        connector.type = "file"
        connector.config = {"system": True}
        connector.status = "active"
        return connector

    @pytest.mark.asyncio
    async def test_get_by_user_and_type_system_found(
        self, crud, mock_session, mock_connector
    ):
        """Test finding a system connector by user and type."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_connector]
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_user_and_type(
            mock_session, 42, "file", system=True
        )

        assert result == mock_connector
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_and_type_system_not_found(
        self, crud, mock_session
    ):
        """Test that non-system connector is not returned when system=True."""
        non_system_connector = MagicMock()
        non_system_connector.config = {}  # No system flag

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [non_system_connector]
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_user_and_type(
            mock_session, 42, "file", system=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_user_and_type_no_connectors(
        self, crud, mock_session
    ):
        """Test when no connectors exist for user."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_user_and_type(
            mock_session, 42, "file", system=True
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_upload_connector_existing(
        self, crud, mock_session, mock_connector
    ):
        """Test getting existing upload connector."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_connector]
        mock_session.execute.return_value = mock_result

        result = await crud.get_or_create_upload_connector(mock_session, 42)

        assert result == mock_connector
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_upload_connector_creates_new(
        self, crud, mock_session
    ):
        """Test creating new upload connector when none exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Mock refresh to simulate DB setting values
        async def mock_refresh(obj):
            obj.id = 1
            obj.creation_date = datetime.now(timezone.utc)

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await crud.get_or_create_upload_connector(mock_session, 42)

        mock_session.add.assert_called_once()
        added_connector = mock_session.add.call_args[0][0]
        assert added_connector.name == "__system_uploads__"
        assert added_connector.type == "file"
        assert added_connector.config == {"system": True}
        assert added_connector.user_id == 42
        assert added_connector.scope == "user"
        assert added_connector.status == "active"

    @pytest.mark.asyncio
    async def test_get_or_create_upload_connector_idempotent(
        self, crud, mock_session, mock_connector
    ):
        """Test that multiple calls return the same connector."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_connector]
        mock_session.execute.return_value = mock_result

        result1 = await crud.get_or_create_upload_connector(mock_session, 42)
        result2 = await crud.get_or_create_upload_connector(mock_session, 42)

        assert result1 == result2
        assert result1 == mock_connector
