"""Unit tests for ChatService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.logic.chat_service import ChatService, RetrievedSource
from api.logic.exceptions import NotFoundError, ServiceUnavailableError


class TestChatServiceGetSession:
    """Tests for ChatService.get_session()."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_qdrant(self) -> MagicMock:
        """Create mock Qdrant client."""
        return MagicMock()

    @pytest.fixture
    def mock_embedder(self) -> AsyncMock:
        """Create mock Embedder client."""
        return AsyncMock()

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def service(
        self,
        mock_db: AsyncMock,
        mock_qdrant: MagicMock,
        mock_embedder: AsyncMock,
        mock_llm: AsyncMock,
    ) -> ChatService:
        """Create ChatService with mocked dependencies."""
        return ChatService(
            db=mock_db,
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            llm=mock_llm,
        )

    @pytest.fixture
    def mock_user(self) -> MagicMock:
        """Create mock user."""
        user = MagicMock()
        user.id = 1
        user.email = "test@example.com"
        return user

    @pytest.mark.asyncio
    async def test_get_session_returns_session(
        self,
        service: ChatService,
        mock_db: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test get_session returns session when found and owned by user."""
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.user_id = mock_user.id
        mock_session.deleted_date = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await service.get_session(1, mock_user)

        assert result == mock_session

    @pytest.mark.asyncio
    async def test_get_session_raises_not_found_when_missing(
        self,
        service: ChatService,
        mock_db: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test get_session raises NotFoundError when session doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError) as exc_info:
            await service.get_session(999, mock_user)

        assert "999" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_session_raises_not_found_for_other_user(
        self,
        service: ChatService,
        mock_db: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test get_session raises NotFoundError when session owned by other user."""
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.user_id = 999  # Different user

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        with pytest.raises(NotFoundError):
            await service.get_session(1, mock_user)


class TestChatServiceRetrieveContext:
    """Tests for ChatService.retrieve_context()."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_qdrant(self) -> AsyncMock:
        """Create mock Qdrant client."""
        return AsyncMock()

    @pytest.fixture
    def mock_embedder(self) -> AsyncMock:
        """Create mock Embedder client."""
        client = AsyncMock()
        client.embed_query.return_value = [0.1, 0.2, 0.3]
        return client

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self) -> MagicMock:
        """Create mock user."""
        user = MagicMock()
        user.id = 1
        return user

    @pytest.fixture
    def service(
        self,
        mock_db: AsyncMock,
        mock_qdrant: AsyncMock,
        mock_embedder: AsyncMock,
        mock_llm: AsyncMock,
    ) -> ChatService:
        """Create ChatService with mocked dependencies."""
        return ChatService(
            db=mock_db,
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            llm=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_sources(
        self,
        service: ChatService,
        mock_qdrant: AsyncMock,
        mock_embedder: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test retrieve_context returns ranked sources from Qdrant."""
        # Mock permissions to return user's collection
        with patch.object(
            service._permissions, "get_search_collections"
        ) as mock_collections:
            mock_collections.return_value = ["user_1"]

            # Mock Qdrant search results
            mock_qdrant.search.return_value = [
                {
                    "id": "chunk_1",
                    "score": 0.95,
                    "payload": {
                        "document_id": 1,
                        "title": "Test Doc",
                        "text": "Test content",
                    },
                },
            ]

            sources = await service.retrieve_context(
                query="test query",
                user=mock_user,
                limit=5,
            )

            assert len(sources) == 1
            assert sources[0].document_id == 1
            assert sources[0].score == 0.95
            mock_embedder.embed_query.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_empty_when_no_collections(
        self,
        service: ChatService,
        mock_user: MagicMock,
    ) -> None:
        """Test retrieve_context returns empty list when user has no collections."""
        with patch.object(
            service._permissions, "get_search_collections"
        ) as mock_collections:
            mock_collections.return_value = []

            sources = await service.retrieve_context(
                query="test query",
                user=mock_user,
            )

            assert sources == []

    @pytest.mark.asyncio
    async def test_retrieve_context_raises_when_embedder_fails(
        self,
        service: ChatService,
        mock_embedder: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test retrieve_context raises ServiceUnavailableError on embedder failure."""
        mock_embedder.embed_query.side_effect = Exception("Connection failed")

        with patch.object(
            service._permissions, "get_search_collections"
        ) as mock_collections:
            mock_collections.return_value = ["user_1"]

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await service.retrieve_context(
                    query="test query",
                    user=mock_user,
                )

            assert "Embedder" in str(exc_info.value)


class TestChatServiceSaveMessages:
    """Tests for ChatService message persistence."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_qdrant(self) -> MagicMock:
        """Create mock Qdrant client."""
        return MagicMock()

    @pytest.fixture
    def mock_embedder(self) -> AsyncMock:
        """Create mock Embedder client."""
        return AsyncMock()

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def service(
        self,
        mock_db: AsyncMock,
        mock_qdrant: MagicMock,
        mock_embedder: AsyncMock,
        mock_llm: AsyncMock,
    ) -> ChatService:
        """Create ChatService with mocked dependencies."""
        return ChatService(
            db=mock_db,
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            llm=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_save_user_message(
        self,
        service: ChatService,
        mock_db: AsyncMock,
    ) -> None:
        """Test save_user_message creates message record."""

        async def set_message_id(msg: MagicMock) -> None:
            msg.id = 1

        mock_db.refresh.side_effect = set_message_id

        message = await service.save_user_message(
            session_id=1,
            content="Hello, world!",
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_assistant_message_with_sources(
        self,
        service: ChatService,
        mock_db: AsyncMock,
    ) -> None:
        """Test save_assistant_message creates message and links sources."""
        sources = [
            RetrievedSource(
                document_id=1,
                chunk_id="chunk_1",
                score=0.95,
                title="Test Doc",
                content="Test content",
            ),
        ]

        async def set_message_id(msg: MagicMock) -> None:
            msg.id = 1

        mock_db.refresh.side_effect = set_message_id

        # Mock session update
        mock_session = MagicMock()
        mock_session.message_count = 0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        message = await service.save_assistant_message(
            session_id=1,
            content="Response content",
            sources=sources,
        )

        # Should add message + 1 source link
        assert mock_db.add.call_count == 2


class TestChatServiceBuildPrompt:
    """Tests for ChatService._build_prompt_messages()."""

    @pytest.fixture
    def service(self) -> ChatService:
        """Create ChatService with mocked dependencies."""
        return ChatService(
            db=AsyncMock(),
            qdrant=MagicMock(),
            embedder=AsyncMock(),
            llm=AsyncMock(),
        )

    def test_build_prompt_includes_system_prompt(
        self,
        service: ChatService,
    ) -> None:
        """Test prompt includes assistant's system prompt."""
        assistant = MagicMock()
        assistant.system_prompt = "You are a helpful assistant."
        assistant.task_prompt = ""

        messages = service._build_prompt_messages(
            assistant=assistant,
            query="What is 2+2?",
            sources=[],
        )

        assert len(messages) >= 2
        assert messages[0].role == "system"
        assert "helpful assistant" in messages[0].content

    def test_build_prompt_includes_context(
        self,
        service: ChatService,
    ) -> None:
        """Test prompt includes retrieved context."""
        assistant = MagicMock()
        assistant.system_prompt = "You are helpful."
        assistant.task_prompt = ""

        sources = [
            RetrievedSource(
                document_id=1,
                chunk_id="chunk_1",
                score=0.95,
                title="Test Doc",
                content="Important information here.",
            ),
        ]

        messages = service._build_prompt_messages(
            assistant=assistant,
            query="Tell me about this",
            sources=sources,
        )

        # System message should include context
        assert "Important information here" in messages[0].content
        assert "Source 1" in messages[0].content

    def test_build_prompt_with_empty_sources(
        self,
        service: ChatService,
    ) -> None:
        """Test prompt works correctly with no sources."""
        assistant = MagicMock()
        assistant.system_prompt = "You are helpful."
        assistant.task_prompt = ""

        messages = service._build_prompt_messages(
            assistant=assistant,
            query="Hello",
            sources=[],
        )

        # Should have system + user message
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello"
        # No context section when no sources
        assert "Relevant Context" not in messages[0].content

    def test_build_prompt_with_task_prompt(
        self,
        service: ChatService,
    ) -> None:
        """Test prompt includes task prompt when present."""
        assistant = MagicMock()
        assistant.system_prompt = "You are helpful."
        assistant.task_prompt = "Always respond in JSON format."

        messages = service._build_prompt_messages(
            assistant=assistant,
            query="List items",
            sources=[],
        )

        # Should have system + task + user messages
        assert len(messages) == 3
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Always respond in JSON format."
        assert messages[2].role == "user"
        assert messages[2].content == "List items"


class TestChatServiceEdgeCases:
    """Edge case tests for ChatService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_qdrant(self) -> AsyncMock:
        """Create mock Qdrant client."""
        return AsyncMock()

    @pytest.fixture
    def mock_embedder(self) -> AsyncMock:
        """Create mock Embedder client."""
        client = AsyncMock()
        client.embed_query.return_value = [0.1, 0.2, 0.3]
        return client

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def mock_user(self) -> MagicMock:
        """Create mock user."""
        user = MagicMock()
        user.id = 1
        return user

    @pytest.fixture
    def service(
        self,
        mock_db: AsyncMock,
        mock_qdrant: AsyncMock,
        mock_embedder: AsyncMock,
        mock_llm: AsyncMock,
    ) -> ChatService:
        """Create ChatService with mocked dependencies."""
        return ChatService(
            db=mock_db,
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            llm=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_retrieve_context_handles_qdrant_collection_error(
        self,
        service: ChatService,
        mock_qdrant: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test retrieve_context continues when a collection search fails."""
        with patch.object(
            service._permissions, "get_search_collections"
        ) as mock_collections:
            mock_collections.return_value = ["user_1", "team_2"]

            # First collection succeeds, second fails
            mock_qdrant.search.side_effect = [
                [{"id": "chunk_1", "score": 0.9, "payload": {"document_id": 1, "title": "Doc", "text": "Content"}}],
                Exception("Collection not found"),
            ]

            sources = await service.retrieve_context(
                query="test query",
                user=mock_user,
            )

            # Should return results from the successful collection
            assert len(sources) == 1
            assert sources[0].document_id == 1

    @pytest.mark.asyncio
    async def test_retrieve_context_handles_all_collections_failing(
        self,
        service: ChatService,
        mock_qdrant: AsyncMock,
        mock_user: MagicMock,
    ) -> None:
        """Test retrieve_context returns empty when all collections fail."""
        with patch.object(
            service._permissions, "get_search_collections"
        ) as mock_collections:
            mock_collections.return_value = ["user_1", "team_2"]

            # All collections fail
            mock_qdrant.search.side_effect = Exception("Collection not found")

            sources = await service.retrieve_context(
                query="test query",
                user=mock_user,
            )

            # Should return empty list, not raise
            assert sources == []

    @pytest.mark.asyncio
    async def test_get_document_titles_with_empty_list(
        self,
        service: ChatService,
    ) -> None:
        """Test get_document_titles returns empty dict for empty input."""
        result = await service.get_document_titles([])
        assert result == {}
