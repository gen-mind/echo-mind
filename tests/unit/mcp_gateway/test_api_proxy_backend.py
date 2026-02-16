"""Unit tests for mcp_gateway.backends.api_proxy_backend."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_gateway.backends.api_key_manager import ApiKeyManager
from mcp_gateway.backends.api_proxy_backend import ApiProxyBackend


@pytest.fixture
def mock_api_key_manager() -> MagicMock:
    """Create a mock ApiKeyManager with Google Search keys configured."""
    mgr = MagicMock(spec=ApiKeyManager)
    mgr.has_key.return_value = True
    mgr.get_key.side_effect = lambda s: {
        "google_search_api_key": "test-api-key",
        "google_search_cx": "test-cx",
    }.get(s, "")
    return mgr


@pytest.fixture
def backend(mock_api_key_manager: MagicMock) -> ApiProxyBackend:
    """Create an ApiProxyBackend with mocked key manager."""
    return ApiProxyBackend(api_key_manager=mock_api_key_manager)


def _make_mock_client(response: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient context manager returning the given response."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)
    return mock_client


class TestApiProxyBackendInit:
    """Tests for ApiProxyBackend initialization."""

    def test_stores_api_key_manager(self, mock_api_key_manager: MagicMock) -> None:
        """Backend stores the provided ApiKeyManager."""
        backend = ApiProxyBackend(api_key_manager=mock_api_key_manager)
        assert backend._api_key_manager is mock_api_key_manager


class TestWebSearch:
    """Tests for ApiProxyBackend.web_search."""

    @pytest.mark.asyncio
    async def test_successful_search(self, backend: ApiProxyBackend) -> None:
        """Successful Google search returns formatted results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Result 1",
                    "link": "https://example.com/1",
                    "snippet": "First result snippet",
                },
                {
                    "title": "Result 2",
                    "link": "https://example.com/2",
                    "snippet": "Second result snippet",
                },
            ]
        }

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=_make_mock_client(mock_response),
        ):
            result = await backend.web_search("test query", max_results=5)

        assert len(result) == 2
        assert result[0]["title"] == "Result 1"
        assert result[0]["link"] == "https://example.com/1"
        assert result[0]["snippet"] == "First result snippet"
        assert result[1]["title"] == "Result 2"

    @pytest.mark.asyncio
    async def test_missing_api_key(self) -> None:
        """Returns error when Google API key is not configured."""
        mgr = MagicMock(spec=ApiKeyManager)
        mgr.has_key.return_value = False
        backend = ApiProxyBackend(api_key_manager=mgr)

        result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "API key" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_missing_cx(self) -> None:
        """Returns error when Google CX is not configured."""
        mgr = MagicMock(spec=ApiKeyManager)
        mgr.has_key.side_effect = lambda k: k == "google_search_api_key"
        backend = ApiProxyBackend(api_key_manager=mgr)

        result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "CX" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_http_error_status(self, backend: ApiProxyBackend) -> None:
        """Returns error when Google API returns non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=_make_mock_client(mock_response),
        ):
            result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "429" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_timeout(self, backend: ApiProxyBackend) -> None:
        """Returns error on request timeout."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "timed out" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_empty_results(self, backend: ApiProxyBackend) -> None:
        """Returns empty list when Google returns no items."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=_make_mock_client(mock_response),
        ):
            result = await backend.web_search("noresults")

        assert result == []

    @pytest.mark.asyncio
    async def test_max_results_clamped(
        self, backend: ApiProxyBackend, mock_api_key_manager: MagicMock
    ) -> None:
        """max_results is clamped to 1-10 range."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [{"title": "R", "link": "L", "snippet": "S"}]}

        mock_client = _make_mock_client(mock_response)

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await backend.web_search("test", max_results=50)

        # Verify the num param was clamped to 10
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["num"] == 10

    @pytest.mark.asyncio
    async def test_http_error_exception(self, backend: ApiProxyBackend) -> None:
        """Returns error on httpx.HTTPError."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection reset"))

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "HTTP error" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_unexpected_exception(self, backend: ApiProxyBackend) -> None:
        """Returns error on unexpected exception."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=RuntimeError("something broke"))

        with patch(
            "mcp_gateway.backends.api_proxy_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await backend.web_search("test")

        assert len(result) == 1
        assert "error" in result[0]
        assert "Unexpected" in result[0]["error"]
