"""
API proxy backend for external API calls.

Handles web search via Google Custom Search JSON API.
All API keys are managed via ApiKeyManager — never exposed.
"""

import logging
from typing import Any

import httpx

from mcp_gateway.backends.api_key_manager import ApiKeyManager

logger = logging.getLogger("echomind-mcp-gateway")

_GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
_HTTP_TIMEOUT = 10.0


class ApiProxyBackend:
    """
    Backend for proxied external API calls.

    Provides web search via Google Custom Search.
    API keys are managed internally and never exposed.
    """

    def __init__(self, api_key_manager: ApiKeyManager) -> None:
        """
        Initialize API proxy backend.

        Args:
            api_key_manager: Manager providing API keys for external services.
        """
        self._api_key_manager = api_key_manager

    async def web_search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """
        Search the web using Google Custom Search.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (1-10).

        Returns:
            List of results with title, link, snippet. On error, list with error dict.
        """
        logger.info(f"🌐 web_search: query='{query[:80]}', max_results={max_results}")

        if not self._api_key_manager.has_key("google_search_api_key"):
            logger.warning("⚠️ web_search: Google Search API key not configured")
            return [{"error": "Google Search API key not configured. Set GOOGLE_SEARCH_API_KEY."}]

        if not self._api_key_manager.has_key("google_search_cx"):
            logger.warning("⚠️ web_search: Google Search CX not configured")
            return [{"error": "Google Search CX not configured. Set GOOGLE_SEARCH_CX."}]

        max_results = max(1, min(max_results, 10))

        params = {
            "key": self._api_key_manager.get_key("google_search_api_key"),
            "cx": self._api_key_manager.get_key("google_search_cx"),
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
