"""Tests for sandbox configuration."""

import os
from unittest.mock import patch

import pytest

from api.sandbox.config import SandboxSettings, get_sandbox_settings


class TestSandboxSettings:
    """Tests for SandboxSettings."""

    def test_default_values(self) -> None:
        """Test default settings values."""
        settings = SandboxSettings()
        assert settings.pool_size == 3
        assert settings.max_instances == 15
        assert settings.idle_timeout == 300
        assert settings.session_timeout == 3600
        assert settings.network == "sandbox"
        assert settings.cpu_limit == 2.0
        assert settings.memory_limit == "2g"
        assert settings.reconciliation_interval == 30

    def test_env_prefix(self) -> None:
        """Test that SANDBOX_ prefix is applied to env vars."""
        env = {
            "SANDBOX_POOL_SIZE": "5",
            "SANDBOX_MAX_INSTANCES": "20",
            "SANDBOX_IDLE_TIMEOUT": "600",
            "SANDBOX_SESSION_TIMEOUT": "7200",
            "SANDBOX_IMAGE": "custom-image:v2",
            "SANDBOX_NETWORK": "custom-net",
            "SANDBOX_CPU_LIMIT": "4.0",
            "SANDBOX_MEMORY_LIMIT": "4g",
            "SANDBOX_RECONCILIATION_INTERVAL": "60",
            "SANDBOX_NATS_URL": "nats://custom:4222",
            "SANDBOX_MCP_URL": "http://custom:8100",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = SandboxSettings()
            assert settings.pool_size == 5
            assert settings.max_instances == 20
            assert settings.idle_timeout == 600
            assert settings.session_timeout == 7200
            assert settings.image == "custom-image:v2"
            assert settings.network == "custom-net"
            assert settings.cpu_limit == 4.0
            assert settings.memory_limit == "4g"
            assert settings.reconciliation_interval == 60
            assert settings.nats_url == "nats://custom:4222"
            assert settings.mcp_url == "http://custom:8100"

    def test_pool_size_validation(self) -> None:
        """Test pool_size bounds validation (minimum 1)."""
        settings = SandboxSettings(pool_size=1)
        assert settings.pool_size == 1

        with pytest.raises(Exception):
            SandboxSettings(pool_size=0)

        with pytest.raises(Exception):
            SandboxSettings(pool_size=51)

    def test_max_instances_validation(self) -> None:
        """Test max_instances bounds validation."""
        with pytest.raises(Exception):
            SandboxSettings(max_instances=0)

        with pytest.raises(Exception):
            SandboxSettings(max_instances=101)


class TestGetSandboxSettings:
    """Tests for settings singleton."""

    @pytest.mark.usefixtures("_reset_sandbox_settings")
    def test_singleton_returns_same_instance(self) -> None:
        """Test that get_sandbox_settings returns cached instance."""
        s1 = get_sandbox_settings()
        s2 = get_sandbox_settings()
        assert s1 is s2
