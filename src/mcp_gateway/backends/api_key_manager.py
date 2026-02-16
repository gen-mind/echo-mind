"""
API key manager for MCP Gateway.

Manages API keys loaded from environment variables. The agent never sees
raw key values — the manager uses them internally when proxying requests.
"""

import logging
import os

logger = logging.getLogger("echomind-mcp-gateway")

# Mapping of service name -> environment variable name
_SERVICE_ENV_MAP: dict[str, str] = {
    "google_search_api_key": "GOOGLE_SEARCH_API_KEY",
    "google_search_cx": "GOOGLE_SEARCH_CX",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


class ApiKeyManager:
    """
    Manages API keys for external service proxying.

    Keys are loaded from environment variables at initialization.
    The agent never receives raw key values — the manager uses them
    internally when proxying API requests.
    """

    def __init__(self) -> None:
        """Load API keys from environment."""
        self._keys: dict[str, str] = {}
        self._load_keys()

    def _load_keys(self) -> None:
        """
        Load known API keys from environment variables.

        Iterates over the service-to-env-var mapping and stores
        any non-empty values found.
        """
        for service, env_var in _SERVICE_ENV_MAP.items():
            value = os.environ.get(env_var, "").strip()
            if value:
                self._keys[service] = value
                logger.info(f"🔑 API key loaded for service: {service}")
            else:
                logger.debug(f"🔒 No API key found for service: {service} (env: {env_var})")

        logger.info(
            f"🔑 ApiKeyManager initialized with {len(self._keys)}/{len(_SERVICE_ENV_MAP)} keys"
        )

    def has_key(self, service: str) -> bool:
        """
        Check if a key is available for a service.

        Args:
            service: Service identifier (e.g. 'google_search_api_key').

        Returns:
            True if the key is configured and non-empty.
        """
        return service in self._keys

    def get_key(self, service: str) -> str:
        """
        Get a key value (internal use only, never exposed to agent).

        Args:
            service: Service identifier (e.g. 'google_search_api_key').

        Returns:
            The API key string.

        Raises:
            KeyError: If no key is configured for the service.
        """
        try:
            return self._keys[service]
        except KeyError:
            raise KeyError(
                f"No API key configured for service '{service}'. "
                f"Set the {_SERVICE_ENV_MAP.get(service, 'UNKNOWN')} environment variable."
            ) from None

    @property
    def available_services(self) -> list[str]:
        """
        List services with configured API keys.

        Returns:
            List of service identifiers that have keys loaded.
        """
        return list(self._keys.keys())
