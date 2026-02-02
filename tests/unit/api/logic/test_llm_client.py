"""Unit tests for LLMClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.logic.exceptions import ServiceUnavailableError
from api.logic.llm_client import ChatMessage, LLMClient, LLMConfig


class TestLLMClientStreamCompletion:
    """Tests for LLMClient.stream_completion()."""

    @pytest.fixture
    def client(self) -> LLMClient:
        """Create LLMClient instance."""
        return LLMClient(timeout=30.0)

    @pytest.fixture
    def openai_config(self) -> LLMConfig:
        """Create OpenAI-compatible config."""
        return LLMConfig(
            provider="openai",
            endpoint="https://api.openai.com",
            model_id="gpt-4",
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def anthropic_config(self) -> LLMConfig:
        """Create Anthropic config."""
        return LLMConfig(
            provider="anthropic",
            endpoint="https://api.anthropic.com",
            model_id="claude-3-opus",
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def messages(self) -> list[ChatMessage]:
        """Create sample messages."""
        return [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="Hello"),
        ]

    @pytest.mark.asyncio
    async def test_stream_openai_compatible(
        self,
        client: LLMClient,
        openai_config: LLMConfig,
        messages: list[ChatMessage],
    ) -> None:
        """Test streaming from OpenAI-compatible API."""
        # Mock httpx response with SSE stream
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_iter_lines():
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" world"}}]}'
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_iter_lines

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncMock())
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        client._client = mock_client

        tokens = []
        async for token in client._stream_openai_compatible(openai_config, messages):
            tokens.append(token)

        assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_anthropic(
        self,
        client: LLMClient,
        anthropic_config: LLMConfig,
        messages: list[ChatMessage],
    ) -> None:
        """Test streaming from Anthropic API."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_iter_lines():
            yield 'data: {"type":"content_block_delta","delta":{"text":"Hi"}}'
            yield 'data: {"type":"content_block_delta","delta":{"text":" there"}}'
            yield 'data: {"type":"message_stop"}'

        mock_response.aiter_lines = mock_iter_lines

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncMock())
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        client._client = mock_client

        tokens = []
        async for token in client._stream_anthropic(anthropic_config, messages):
            tokens.append(token)

        assert tokens == ["Hi", " there"]

    @pytest.mark.asyncio
    async def test_stream_anthropic_passes_temperature(
        self,
        client: LLMClient,
        messages: list[ChatMessage],
    ) -> None:
        """Test Anthropic API request includes temperature parameter."""
        config = LLMConfig(
            provider="anthropic",
            endpoint="https://api.anthropic.com",
            model_id="claude-3-opus",
            api_key="test-key",
            max_tokens=1024,
            temperature=0.3,  # Specific value to verify
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_iter_lines():
            yield 'data: {"type":"message_stop"}'

        mock_response.aiter_lines = mock_iter_lines

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncMock())
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        client._client = mock_client

        tokens = []
        async for token in client._stream_anthropic(config, messages):
            tokens.append(token)

        # Verify temperature was passed in the request payload
        call_args = mock_client.stream.call_args
        json_payload = call_args.kwargs.get("json", {})
        assert json_payload.get("temperature") == 0.3

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises_error(
        self,
        client: LLMClient,
        messages: list[ChatMessage],
    ) -> None:
        """Test unsupported provider raises ServiceUnavailableError."""
        bad_config = LLMConfig(
            provider="unknown_provider",
            endpoint="https://example.com",
            model_id="model",
            api_key=None,
            max_tokens=100,
            temperature=0.5,
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            tokens = []
            async for token in client.stream_completion(bad_config, messages):
                tokens.append(token)

        assert "unknown_provider" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_api_error_raises_service_unavailable(
        self,
        client: LLMClient,
        openai_config: LLMConfig,
        messages: list[ChatMessage],
    ) -> None:
        """Test API error response raises ServiceUnavailableError."""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        async def mock_aread():
            return b'{"error": "Internal server error"}'

        mock_response.aread = mock_aread

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncMock())
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        client._client = mock_client

        with pytest.raises(ServiceUnavailableError):
            tokens = []
            async for token in client._stream_openai_compatible(openai_config, messages):
                tokens.append(token)


class TestLLMClientClose:
    """Tests for LLMClient.close()."""

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self) -> None:
        """Test close properly closes HTTP client."""
        client = LLMClient()
        mock_http_client = AsyncMock()
        client._client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_safe_when_no_client(self) -> None:
        """Test close is safe when no client initialized."""
        client = LLMClient()
        await client.close()  # Should not raise
