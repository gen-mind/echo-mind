"""Unit tests for mcp_gateway.backends.api_key_manager."""

from unittest.mock import patch

import pytest

from mcp_gateway.backends.api_key_manager import ApiKeyManager


class TestApiKeyManagerInit:
    """Tests for ApiKeyManager initialization."""

    def test_loads_keys_from_environment(self) -> None:
        """Keys present in environment are loaded."""
        env = {
            "GOOGLE_SEARCH_API_KEY": "goog-key",
            "GOOGLE_SEARCH_CX": "cx-123",
        }
        with patch.dict("os.environ", env, clear=False):
            mgr = ApiKeyManager()

        assert mgr.has_key("google_search_api_key")
        assert mgr.has_key("google_search_cx")

    def test_skips_empty_values(self) -> None:
        """Empty or whitespace-only env vars are not loaded."""
        env = {
            "GOOGLE_SEARCH_API_KEY": "",
            "GOOGLE_SEARCH_CX": "   ",
        }
        with patch.dict("os.environ", env, clear=False):
            mgr = ApiKeyManager()

        assert not mgr.has_key("google_search_api_key")
        assert not mgr.has_key("google_search_cx")

    def test_missing_env_vars(self) -> None:
        """Missing env vars result in no keys loaded."""
        with patch.dict("os.environ", {}, clear=True):
            mgr = ApiKeyManager()

        assert mgr.available_services == []


class TestApiKeyManagerAccess:
    """Tests for ApiKeyManager key access."""

    @pytest.fixture
    def manager(self) -> ApiKeyManager:
        """Create a manager with known keys."""
        env = {"GOOGLE_SEARCH_API_KEY": "test-key-123"}
        with patch.dict("os.environ", env, clear=False):
            return ApiKeyManager()

    def test_get_key_returns_value(self, manager: ApiKeyManager) -> None:
        """get_key returns the actual key value."""
        assert manager.get_key("google_search_api_key") == "test-key-123"

    def test_get_key_raises_for_missing(self, manager: ApiKeyManager) -> None:
        """get_key raises KeyError for unconfigured services."""
        with pytest.raises(KeyError, match="No API key configured"):
            manager.get_key("nonexistent_service")

    def test_has_key_true_for_loaded(self, manager: ApiKeyManager) -> None:
        """has_key returns True for loaded keys."""
        assert manager.has_key("google_search_api_key") is True

    def test_has_key_false_for_missing(self) -> None:
        """has_key returns False for missing keys."""
        with patch.dict("os.environ", {}, clear=True):
            mgr = ApiKeyManager()
        assert mgr.has_key("openai_api_key") is False

    def test_available_services(self, manager: ApiKeyManager) -> None:
        """available_services lists loaded service names."""
        services = manager.available_services
        assert "google_search_api_key" in services
