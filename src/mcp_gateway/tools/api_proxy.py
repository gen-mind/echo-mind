"""
API proxy tools for MCP Gateway.

Registers MCP tool definitions for web search operations.
Thin adapter layer — all business logic lives in ApiProxyBackend.
"""

from typing import Any

from fastmcp import FastMCP

from mcp_gateway.backends.api_proxy_backend import ApiProxyBackend


def register_api_proxy_tools(mcp: FastMCP, api_proxy_backend: ApiProxyBackend) -> None:
    """
    Register API proxy MCP tools on the FastMCP server.

    Defines tools for web search via Google Custom Search JSON API.

    Args:
        mcp: FastMCP server instance to register tools on.
        api_proxy_backend: Backend handling external API calls.
    """

    @mcp.tool()
    async def web_search(
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search the web using Google Custom Search.

        Performs a web search and returns titles, links, and snippets.
        API keys are managed internally and never exposed.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (default: 5, max: 10).

        Returns:
            List of search results with 'title', 'link', and 'snippet' fields.
            On error, returns a list with a single dict containing an 'error' key.
        """
        return await api_proxy_backend.web_search(query, max_results)
