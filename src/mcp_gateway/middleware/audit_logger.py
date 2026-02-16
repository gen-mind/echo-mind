"""
Structured JSON audit logging middleware for MCP tool invocations.

Provides a FastMCP Middleware subclass that intercepts ``tools/call`` requests,
logs structured JSON entries to stdout (for Docker log aggregation), and
automatically redacts sensitive parameter values.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger("echomind-mcp-audit")

_SENSITIVE_SUBSTRINGS: frozenset[str] = frozenset(
    {"token", "secret", "password", "api_key", "apikey", "credential", "auth"}
)

_REDACTED: str = "[REDACTED]"


def redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy and redact sensitive values from a dictionary.

    Any key whose **lowercased** name contains one of the sensitive
    substrings (``token``, ``secret``, ``password``, ``api_key``,
    ``apikey``, ``credential``, ``auth``) will have its value replaced
    with ``[REDACTED]``.
    Nested dicts and lists of dicts are handled recursively.

    Args:
        data: Dictionary to redact.  The original is never mutated.

    Returns:
        A new dictionary with sensitive values replaced.
    """
    redacted = copy.deepcopy(data)
    _redact_in_place(redacted)
    return redacted


def _redact_in_place(obj: Any) -> None:
    """Recursively redact sensitive values in-place.

    Args:
        obj: Object to inspect and redact.  Only ``dict`` and ``list``
            instances are traversed.
    """
    if isinstance(obj, dict):
        for k in obj:
            lower_key = k.lower()
            if any(s in lower_key for s in _SENSITIVE_SUBSTRINGS):
                obj[k] = _REDACTED
            else:
                _redact_in_place(obj[k])
    elif isinstance(obj, list):
        for item in obj:
            _redact_in_place(item)


class AuditLoggingMiddleware(Middleware):
    """FastMCP middleware that emits structured JSON audit logs for every tool call.

    Hooks into the ``on_call_tool`` dispatch point so that each tool
    invocation is logged with:

    * ISO-8601 timestamp (UTC)
    * tool name
    * redacted parameters
    * result status (``success`` / ``error``)
    * duration in milliseconds
    * error message (if any)

    Logs are written to the ``echomind-mcp-audit`` logger at INFO level
    as single-line JSON, making them easy to aggregate in Docker / ELK.

    Example::

        from fastmcp import FastMCP
        from mcp_gateway.middleware.audit_logger import AuditLoggingMiddleware

        mcp = FastMCP("echomind-mcp-gateway")
        mcp.add_middleware(AuditLoggingMiddleware())
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls, measure execution, and emit audit log.

        Args:
            context: Middleware context wrapping the ``CallToolRequestParams``.
            call_next: Next handler in the middleware chain.

        Returns:
            The ``ToolResult`` produced by the downstream handler.

        Raises:
            Exception: Re-raises any exception from the tool after logging it.
        """
        tool_name: str = context.message.name
        parameters: dict[str, Any] = context.message.arguments or {}
        redacted_params: dict[str, Any] = redact_sensitive(parameters)

        start: float = time.monotonic()
        try:
            result: ToolResult = await call_next(context)
            duration_ms: float = round((time.monotonic() - start) * 1000, 2)

            _emit_audit_entry(
                tool=tool_name,
                parameters=redacted_params,
                result_status="success",
                duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _emit_audit_entry(
                tool=tool_name,
                parameters=redacted_params,
                result_status="error",
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise


def _emit_audit_entry(
    *,
    tool: str,
    parameters: dict[str, Any],
    result_status: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """Write a single structured JSON audit entry to the audit logger.

    Args:
        tool: Name of the MCP tool that was invoked.
        parameters: Redacted copy of the tool's input parameters.
        result_status: ``"success"`` or ``"error"``.
        duration_ms: Wall-clock duration of the tool call in milliseconds.
        error: Error message string, or ``None`` on success.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "mcp_tool_call",
        "tool": tool,
        "parameters": parameters,
        "result_status": result_status,
        "duration_ms": duration_ms,
        "error": error,
        "request_id": None,  # TODO: Extract from MCP request context in Phase 8
    }
    logger.info(json.dumps(entry, default=str))
