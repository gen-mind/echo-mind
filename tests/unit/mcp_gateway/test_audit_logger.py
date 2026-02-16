"""Unit tests for mcp_gateway.middleware.audit_logger."""

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import mcp.types as mt
import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult

from mcp_gateway.middleware.audit_logger import (
    AuditLoggingMiddleware,
    _emit_audit_entry,
    redact_sensitive,
)


class TestRedactSensitive:
    """Tests for redact_sensitive utility."""

    def test_redacts_token_key(self) -> None:
        """Keys containing 'token' are redacted."""
        data = {"access_token": "abc123", "name": "test"}
        result = redact_sensitive(data)
        assert result["access_token"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_redacts_secret_key(self) -> None:
        """Keys containing 'secret' are redacted."""
        data = {"client_secret": "xyz"}
        result = redact_sensitive(data)
        assert result["client_secret"] == "[REDACTED]"

    def test_redacts_password_key(self) -> None:
        """Keys containing 'password' are redacted."""
        data = {"password": "hunter2", "user_password": "abc"}
        result = redact_sensitive(data)
        assert result["password"] == "[REDACTED]"
        assert result["user_password"] == "[REDACTED]"

    def test_redacts_key_key(self) -> None:
        """Keys containing 'api_key' are redacted, but 'monkey' is not."""
        data = {"api_key": "sk-xxx", "monkey": "business"}
        result = redact_sensitive(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["monkey"] == "business"

    def test_redacts_credential_key(self) -> None:
        """Keys containing 'credential' are redacted."""
        data = {"credential_file": "/path"}
        result = redact_sensitive(data)
        assert result["credential_file"] == "[REDACTED]"

    def test_redacts_auth_key(self) -> None:
        """Keys containing 'auth' are redacted."""
        data = {"auth_header": "Bearer xxx", "author": "John"}
        result = redact_sensitive(data)
        assert result["auth_header"] == "[REDACTED]"
        assert result["author"] == "[REDACTED]"

    def test_case_insensitive(self) -> None:
        """Redaction is case-insensitive."""
        data = {"API_TOKEN": "val", "Secret_Key": "val2"}
        result = redact_sensitive(data)
        assert result["API_TOKEN"] == "[REDACTED]"
        assert result["Secret_Key"] == "[REDACTED]"

    def test_nested_dict_redaction(self) -> None:
        """Nested dicts are recursively redacted."""
        data = {"config": {"auth_token": "tok", "host": "localhost"}}
        result = redact_sensitive(data)
        assert result["config"]["auth_token"] == "[REDACTED]"
        assert result["config"]["host"] == "localhost"

    def test_list_of_dicts_redaction(self) -> None:
        """Lists containing dicts are recursively redacted."""
        data = {"items": [{"password": "p1"}, {"name": "safe"}]}
        result = redact_sensitive(data)
        assert result["items"][0]["password"] == "[REDACTED]"
        assert result["items"][1]["name"] == "safe"

    def test_does_not_mutate_original(self) -> None:
        """Original dict is not mutated."""
        data = {"api_key": "original_value"}
        redact_sensitive(data)
        assert data["api_key"] == "original_value"

    def test_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        assert redact_sensitive({}) == {}

    def test_no_sensitive_keys(self) -> None:
        """Dict with no sensitive keys is returned unchanged."""
        data = {"query": "test", "limit": 10}
        result = redact_sensitive(data)
        assert result == data


class TestEmitAuditEntry:
    """Tests for _emit_audit_entry helper."""

    def test_emits_success_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        """Success entries are logged as structured JSON."""
        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            _emit_audit_entry(
                tool="search_documents",
                parameters={"query": "test"},
                result_status="success",
                duration_ms=123.45,
            )

        assert len(caplog.records) == 1
        entry = json.loads(caplog.records[0].message)
        assert entry["event"] == "mcp_tool_call"
        assert entry["tool"] == "search_documents"
        assert entry["parameters"] == {"query": "test"}
        assert entry["result_status"] == "success"
        assert entry["duration_ms"] == 123.45
        assert entry["error"] is None

    def test_emits_error_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        """Error entries include the error message."""
        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            _emit_audit_entry(
                tool="failing_tool",
                parameters={},
                result_status="error",
                duration_ms=50.0,
                error="Connection refused",
            )

        entry = json.loads(caplog.records[0].message)
        assert entry["result_status"] == "error"
        assert entry["error"] == "Connection refused"

    def test_entry_has_timestamp(self, caplog: pytest.LogCaptureFixture) -> None:
        """Audit entries include an ISO timestamp."""
        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            _emit_audit_entry(
                tool="t",
                parameters={},
                result_status="success",
                duration_ms=0,
            )

        entry = json.loads(caplog.records[0].message)
        assert "timestamp" in entry
        assert "T" in entry["timestamp"]  # ISO format


class TestAuditLoggingMiddleware:
    """Tests for AuditLoggingMiddleware.on_call_tool."""

    @pytest.fixture
    def middleware(self) -> AuditLoggingMiddleware:
        """Create middleware instance."""
        return AuditLoggingMiddleware()

    @pytest.fixture
    def make_context(self) -> Any:
        """Factory for creating tool call middleware contexts."""

        def _make(
            tool_name: str = "test_tool",
            arguments: dict[str, Any] | None = None,
        ) -> MiddlewareContext[mt.CallToolRequestParams]:
            params = MagicMock(spec=mt.CallToolRequestParams)
            params.name = tool_name
            params.arguments = arguments or {}
            return MiddlewareContext(
                message=params,
                method="tools/call",
            )

        return _make

    @pytest.mark.asyncio
    async def test_logs_successful_call(
        self,
        middleware: AuditLoggingMiddleware,
        make_context: Any,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Successful tool calls are logged with status 'success'."""
        ctx = make_context("search_documents", {"query": "test"})
        call_next = AsyncMock(return_value="result_data")

        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            result = await middleware.on_call_tool(ctx, call_next)

        assert result == "result_data"
        call_next.assert_awaited_once_with(ctx)

        entry = json.loads(caplog.records[0].message)
        assert entry["tool"] == "search_documents"
        assert entry["result_status"] == "success"
        assert entry["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_logs_failed_call_and_reraises(
        self,
        middleware: AuditLoggingMiddleware,
        make_context: Any,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Failed tool calls are logged with status 'error' and re-raised."""
        ctx = make_context("failing_tool")
        call_next = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            caplog.at_level(logging.INFO, logger="echomind-mcp-audit"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await middleware.on_call_tool(ctx, call_next)

        entry = json.loads(caplog.records[0].message)
        assert entry["tool"] == "failing_tool"
        assert entry["result_status"] == "error"
        assert entry["error"] == "boom"

    @pytest.mark.asyncio
    async def test_redacts_sensitive_parameters(
        self,
        middleware: AuditLoggingMiddleware,
        make_context: Any,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Sensitive parameter values are redacted in logs."""
        ctx = make_context(
            "auth_tool", {"api_key": "sk-secret", "query": "safe"}
        )
        call_next = AsyncMock(return_value="ok")

        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            await middleware.on_call_tool(ctx, call_next)

        entry = json.loads(caplog.records[0].message)
        assert entry["parameters"]["api_key"] == "[REDACTED]"
        assert entry["parameters"]["query"] == "safe"

    @pytest.mark.asyncio
    async def test_handles_none_arguments(
        self,
        middleware: AuditLoggingMiddleware,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Handles tools with None arguments gracefully."""
        params = MagicMock(spec=mt.CallToolRequestParams)
        params.name = "no_args_tool"
        params.arguments = None
        ctx = MiddlewareContext(message=params, method="tools/call")
        call_next = AsyncMock(return_value="ok")

        with caplog.at_level(logging.INFO, logger="echomind-mcp-audit"):
            result = await middleware.on_call_tool(ctx, call_next)

        assert result == "ok"
        entry = json.loads(caplog.records[0].message)
        assert entry["parameters"] == {}
