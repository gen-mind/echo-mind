"""
Unit tests for web tools.

Tests cover HTTP request tool with all edge cases.
Target: 100% code coverage
"""

import urllib.error
import urllib.request
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.web import create_http_request_tool


class TestHttpRequestTool:
    """Tests for HTTP request tool."""

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_get_success(self, mock_urlopen):
        """Test successful GET request."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json", "content-length": "13"}
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        tool = create_http_request_tool()
        result = tool("https://example.com/api")

        assert "HTTP 200" in result
        assert '{"ok": true}' in result
        assert "content-type: application/json" in result

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_post_success(self, mock_urlopen):
        """Test successful POST request."""
        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        tool = create_http_request_tool()
        result = tool("https://example.com/api", method="POST", body='{"name": "test"}')

        assert "HTTP 201" in result
        assert '{"id": 1}' in result

    def test_http_invalid_method(self):
        """Test that only GET and POST are allowed."""
        tool = create_http_request_tool()
        result = tool("https://example.com", method="DELETE")

        assert "❌ Error" in result
        assert "Only GET and POST" in result

    def test_http_sensitive_headers_blocked(self):
        """Test that sensitive headers are blocked."""
        tool = create_http_request_tool()

        for header in ["Authorization", "Cookie", "X-Api-Key"]:
            result = tool("https://example.com", headers={header: "value"})
            assert "❌ Error" in result
            assert "Sensitive headers" in result

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_timeout(self, mock_urlopen):
        """Test request timeout handling."""
        mock_urlopen.side_effect = TimeoutError("timed out")

        tool = create_http_request_tool()
        result = tool("https://example.com", timeout=5)

        assert "❌ Error" in result
        assert "timed out" in result

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_body_truncation(self, mock_urlopen):
        """Test that large response bodies are truncated."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read.return_value = ("x" * 15000).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        tool = create_http_request_tool()
        result = tool("https://example.com")

        assert "truncated" in result.lower()

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_connection_error(self, mock_urlopen):
        """Test connection error handling."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        tool = create_http_request_tool()
        result = tool("https://unreachable.example.com")

        assert "❌ Error" in result
        assert "Connection refused" in result

    def test_http_invalid_url(self):
        """Test invalid URL handling."""
        tool = create_http_request_tool()
        result = tool("not-a-url")

        # urllib will raise an error for invalid URLs
        assert "❌ Error" in result

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_post_with_body(self, mock_urlopen):
        """Test POST with body encodes correctly."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read.return_value = b"ok"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        tool = create_http_request_tool()
        result = tool("https://example.com/api", method="POST", body="data=test")

        assert "HTTP 200" in result
        # Verify the request was built with data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.data == b"data=test"
        assert req.method == "POST"

    def test_http_default_params(self):
        """Test that default parameters are correct."""
        tool = create_http_request_tool()

        # Verify function signature defaults
        import inspect
        sig = inspect.signature(tool)
        assert sig.parameters["method"].default == "GET"
        assert sig.parameters["body"].default is None
        assert sig.parameters["headers"].default is None
        assert sig.parameters["timeout"].default == 30

    @patch("src.agent.tools.web.urllib.request.urlopen")
    def test_http_error_response(self, mock_urlopen):
        """Test HTTP error response (4xx/5xx)."""
        error = urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=BytesIO(b"Not Found"),
        )
        mock_urlopen.side_effect = error

        tool = create_http_request_tool()
        result = tool("https://example.com/missing")

        assert "HTTP 404" in result
        assert "Not Found" in result
