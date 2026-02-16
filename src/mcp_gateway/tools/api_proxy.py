"""
API proxy tools for MCP Gateway.

Registers MCP tool definitions for web search, email, and calendar
operations. The agent never sees raw API keys — all external API
calls are proxied through the ApiKeyManager.
"""

import logging
from typing import Any

import httpx
from fastmcp import FastMCP

from mcp_gateway.backends.api_key_manager import ApiKeyManager

logger = logging.getLogger("echomind-mcp-gateway")

_GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_HTTP_TIMEOUT = 10.0
_OAUTH_STUB_MESSAGE = (
    "This feature requires user OAuth tokens, which will be available in Phase 8. "
    "Please configure OAuth integration to enable this capability."
)


def register_api_proxy_tools(mcp: FastMCP, api_key_manager: ApiKeyManager) -> None:
    """
    Register API proxy MCP tools on the FastMCP server.

    Defines tools for web search, email sending, and calendar operations.
    Web search is fully implemented via Google Custom Search JSON API.
    Email and calendar tools are stubs pending OAuth integration.

    Args:
        mcp: FastMCP server instance to register tools on.
        api_key_manager: ApiKeyManager providing API keys for external services.
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
        logger.info(f"🌐 web_search: query='{query[:80]}', max_results={max_results}")

        if not api_key_manager.has_key("google_search_api_key"):
            logger.warning("⚠️ web_search: Google Search API key not configured")
            return [{"error": "Google Search API key not configured. Set GOOGLE_SEARCH_API_KEY."}]

        if not api_key_manager.has_key("google_search_cx"):
            logger.warning("⚠️ web_search: Google Search CX not configured")
            return [{"error": "Google Search CX not configured. Set GOOGLE_SEARCH_CX."}]

        max_results = max(1, min(max_results, 10))

        params = {
            "key": api_key_manager.get_key("google_search_api_key"),
            "cx": api_key_manager.get_key("google_search_cx"),
            "q": query,
            "num": max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(_GOOGLE_SEARCH_URL, params=params)

            if response.status_code != 200:
                logger.error(f"❌ web_search: Google API returned {response.status_code}")
                return [{"error": f"Google Search API error (HTTP {response.status_code})"}]

            data = response.json()
            items = data.get("items", [])

            if not items:
                logger.info("🔍 web_search: no results found")
                return []

            results = [
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in items
            ]

            logger.info(f"✅ web_search: returned {len(results)} results")
            return results

        except httpx.TimeoutException:
            logger.error("❌ web_search: request timed out")
            return [{"error": "Google Search API request timed out"}]
        except httpx.HTTPError as e:
            logger.error(f"❌ web_search: HTTP error: {e}")
            return [{"error": f"Google Search API HTTP error: {e}"}]
        except Exception as e:
            logger.exception(f"❌ web_search: unexpected error: {e}")
            return [{"error": f"Unexpected error during web search: {e}"}]

    @mcp.tool()
    async def send_email(
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, str]:
        """
        Send an email on behalf of the user.

        Currently a stub — requires user OAuth tokens (Phase 8).

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body text.

        Returns:
            Status message indicating the feature is not yet available.
        """
        logger.info(f"📧 send_email: to='{to}', subject='{subject[:50]}'")
        return {"status": "unavailable", "message": _OAUTH_STUB_MESSAGE}

    @mcp.tool()
    async def calendar_create_event(
        title: str,
        start: str,
        end: str,
        description: str | None = None,
    ) -> dict[str, str]:
        """
        Create a calendar event.

        Currently a stub — requires user OAuth tokens (Phase 8).

        Args:
            title: Event title.
            start: Event start time (ISO 8601 format).
            end: Event end time (ISO 8601 format).
            description: Optional event description.

        Returns:
            Status message indicating the feature is not yet available.
        """
        logger.info(f"📅 calendar_create_event: title='{title}', start='{start}'")
        return {"status": "unavailable", "message": _OAUTH_STUB_MESSAGE}

    @mcp.tool()
    async def calendar_list_events(
        days_ahead: int = 7,
    ) -> dict[str, str]:
        """
        List upcoming calendar events.

        Currently a stub — requires user OAuth tokens (Phase 8).

        Args:
            days_ahead: Number of days ahead to look for events (default: 7).

        Returns:
            Status message indicating the feature is not yet available.
        """
        logger.info(f"📅 calendar_list_events: days_ahead={days_ahead}")
        return {"status": "unavailable", "message": _OAUTH_STUB_MESSAGE}
