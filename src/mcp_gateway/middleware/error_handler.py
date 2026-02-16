"""
Error handling middleware for MCP Gateway.

Catches domain exceptions from tool handlers and converts them
into user-friendly error responses without leaking internal details.
"""

from __future__ import annotations

import logging
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from mcp_gateway.skills.exceptions import (
    SkillExecutionError,
    SkillNotFoundError,
    SkillTimeoutError,
)

logger = logging.getLogger("echomind-mcp-gateway")


class ErrorHandlingMiddleware(Middleware):
    """FastMCP middleware that converts domain exceptions to safe error responses.

    Catches known exception types and returns structured error messages.
    Unknown exceptions are logged and returned as generic errors to
    prevent internal details from leaking to the agent.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls and handle exceptions gracefully.

        Args:
            context: Middleware context wrapping the ``CallToolRequestParams``.
            call_next: Next handler in the middleware chain.

        Returns:
            The ``ToolResult`` from downstream, or an error ToolResult on failure.
        """
        tool_name: str = context.message.name
        try:
            return await call_next(context)
        except SkillNotFoundError as e:
            logger.warning(f"⚠️ Skill not found during '{tool_name}': {e}")
            return ToolResult(content=[mt.TextContent(type="text", text=f"Skill not found: {e}")])
        except SkillTimeoutError as e:
            logger.warning(f"⏰ Skill timeout during '{tool_name}': {e}")
            return ToolResult(content=[mt.TextContent(type="text", text=f"Skill timed out: {e}")])
        except SkillExecutionError as e:
            logger.error(f"❌ Skill execution error during '{tool_name}': {e}")
            return ToolResult(content=[mt.TextContent(type="text", text=f"Skill execution failed: {e}")])
        except Exception as e:
            logger.error(f"❌ Unhandled error in tool '{tool_name}': {e}", exc_info=True)
            return ToolResult(
                content=[mt.TextContent(type="text", text="An internal error occurred. Please try again later.")]
            )
