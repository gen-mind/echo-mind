"""Tests for sandbox service configuration (src/sandbox/config.py)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from sandbox.config import SandboxSettings


class TestSandboxServiceSettings:
    """Tests for SandboxSettings (sandbox service config)."""

    def test_default_values(self) -> None:
        """Test default settings values."""
        settings = SandboxSettings()
        assert settings.nats_url == "nats://nats:4222"
        assert settings.mcp_url == "http://mcp-server:8080"
        assert settings.session_id == ""
        assert settings.user_id == 0
        assert settings.mode == "warm"
        assert settings.llm_provider == "openai"
        assert settings.llm_model == "gpt-4o"
        assert settings.llm_api_key == ""
        assert settings.llm_endpoint == "https://api.openai.com/v1"
        assert settings.agent_instructions == "You are EchoMind Assistant."
        assert settings.max_turns == 50
        assert settings.timeout_seconds == 300
        assert settings.log_level == "INFO"
        assert settings.health_port == 8080
        assert settings.heartbeat_interval == 15

    def test_env_prefix(self) -> None:
        """Test that SANDBOX_ prefix is applied to all env vars."""
        env = {
            "SANDBOX_NATS_URL": "nats://custom:4222",
            "SANDBOX_MCP_URL": "http://custom-mcp:9090",
            "SANDBOX_SESSION_ID": "sess-001",
            "SANDBOX_USER_ID": "42",
            "SANDBOX_MODE": "active",
            "SANDBOX_LLM_PROVIDER": "anthropic",
            "SANDBOX_LLM_MODEL": "claude-3-opus",
            "SANDBOX_LLM_API_KEY": "sk-test-key",
            "SANDBOX_LLM_ENDPOINT": "https://api.anthropic.com/v1",
            "SANDBOX_AGENT_INSTRUCTIONS": "Custom instructions",
            "SANDBOX_MAX_TURNS": "25",
            "SANDBOX_TIMEOUT_SECONDS": "600",
            "SANDBOX_LOG_LEVEL": "DEBUG",
            "SANDBOX_HEALTH_PORT": "9090",
            "SANDBOX_HEARTBEAT_INTERVAL": "30",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = SandboxSettings()
            assert settings.nats_url == "nats://custom:4222"
            assert settings.mcp_url == "http://custom-mcp:9090"
            assert settings.session_id == "sess-001"
            assert settings.user_id == 42
            assert settings.mode == "active"
            assert settings.llm_provider == "anthropic"
            assert settings.llm_model == "claude-3-opus"
            assert settings.llm_api_key == "sk-test-key"
            assert settings.llm_endpoint == "https://api.anthropic.com/v1"
            assert settings.agent_instructions == "Custom instructions"
            assert settings.max_turns == 25
            assert settings.timeout_seconds == 600
            assert settings.log_level == "DEBUG"
            assert settings.health_port == 9090
            assert settings.heartbeat_interval == 30

    def test_partial_override(self) -> None:
        """Test only provided env vars override defaults."""
        env = {"SANDBOX_SESSION_ID": "partial", "SANDBOX_MODE": "active"}
        with patch.dict(os.environ, env, clear=False):
            settings = SandboxSettings()
            assert settings.session_id == "partial"
            assert settings.mode == "active"
            assert settings.nats_url == "nats://nats:4222"  # unchanged
            assert settings.llm_provider == "openai"  # unchanged

    def test_user_id_is_int(self) -> None:
        """Test that user_id is parsed as int from env."""
        env = {"SANDBOX_USER_ID": "99"}
        with patch.dict(os.environ, env, clear=False):
            settings = SandboxSettings()
            assert settings.user_id == 99
            assert isinstance(settings.user_id, int)
