"""Tests for MCP Gateway configuration."""

import pytest
from pydantic import ValidationError

from mcp_gateway.config import MCPGatewaySettings, get_settings, reset_settings


class TestMCPGatewaySettings:
    """Tests for MCPGatewaySettings Pydantic model."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All defaults are applied when no env vars are set."""
        # Clear any MCP_GATEWAY_ env vars that might exist
        for key in list(monkeypatch._env_patcher.items()) if hasattr(monkeypatch, "_env_patcher") else []:
            pass

        settings = MCPGatewaySettings()  # type: ignore[call-arg]

        assert settings.enabled is True
        assert settings.health_port == 8080
        assert settings.mcp_port == 8100
        assert settings.log_level == "INFO"
        assert settings.qdrant_host == "localhost"
        assert settings.qdrant_port == 6333
        assert settings.qdrant_api_key is None
        assert settings.embedder_host == "localhost"
        assert settings.embedder_port == 50051
        assert settings.embedder_timeout == 30.0
        assert settings.skills_dir == "/app/config/skills"
        assert settings.skill_execution_timeout == 30
        assert settings.skill_max_output_bytes == 65536

    def test_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings are loaded from MCP_GATEWAY_ prefixed env vars."""
        monkeypatch.setenv("MCP_GATEWAY_ENABLED", "false")
        monkeypatch.setenv("MCP_GATEWAY_HEALTH_PORT", "9090")
        monkeypatch.setenv("MCP_GATEWAY_MCP_PORT", "8200")
        monkeypatch.setenv("MCP_GATEWAY_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("MCP_GATEWAY_QDRANT_HOST", "qdrant-server")
        monkeypatch.setenv("MCP_GATEWAY_QDRANT_PORT", "6334")
        monkeypatch.setenv("MCP_GATEWAY_QDRANT_API_KEY", "secret-key")
        monkeypatch.setenv("MCP_GATEWAY_EMBEDDER_HOST", "embedder-server")
        monkeypatch.setenv("MCP_GATEWAY_EMBEDDER_PORT", "50052")
        monkeypatch.setenv("MCP_GATEWAY_EMBEDDER_TIMEOUT", "60.0")
        monkeypatch.setenv("MCP_GATEWAY_SKILLS_DIR", "/custom/skills")
        monkeypatch.setenv("MCP_GATEWAY_SKILL_EXECUTION_TIMEOUT", "60")
        monkeypatch.setenv("MCP_GATEWAY_SKILL_MAX_OUTPUT_BYTES", "131072")

        settings = MCPGatewaySettings()  # type: ignore[call-arg]

        assert settings.enabled is False
        assert settings.health_port == 9090
        assert settings.mcp_port == 8200
        assert settings.log_level == "DEBUG"
        assert settings.qdrant_host == "qdrant-server"
        assert settings.qdrant_port == 6334
        assert settings.qdrant_api_key.get_secret_value() == "secret-key"
        assert settings.embedder_host == "embedder-server"
        assert settings.embedder_port == 50052
        assert settings.embedder_timeout == 60.0
        assert settings.skills_dir == "/custom/skills"
        assert settings.skill_execution_timeout == 60
        assert settings.skill_max_output_bytes == 131072

    def test_extra_fields_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown env vars with the prefix are ignored (extra='ignore')."""
        monkeypatch.setenv("MCP_GATEWAY_UNKNOWN_FIELD", "should-not-error")

        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert not hasattr(settings, "unknown_field")

    def test_skill_execution_timeout_must_be_positive(self) -> None:
        """skill_execution_timeout rejects zero or negative values."""
        with pytest.raises(ValidationError, match="skill_execution_timeout"):
            MCPGatewaySettings(skill_execution_timeout=0)  # type: ignore[call-arg]

        with pytest.raises(ValidationError, match="skill_execution_timeout"):
            MCPGatewaySettings(skill_execution_timeout=-1)  # type: ignore[call-arg]

    def test_skill_max_output_bytes_must_be_positive(self) -> None:
        """skill_max_output_bytes rejects zero or negative values."""
        with pytest.raises(ValidationError, match="skill_max_output_bytes"):
            MCPGatewaySettings(skill_max_output_bytes=0)  # type: ignore[call-arg]

    def test_boolean_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """String boolean values are correctly coerced."""
        monkeypatch.setenv("MCP_GATEWAY_ENABLED", "true")
        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert settings.enabled is True

        reset_settings()
        monkeypatch.setenv("MCP_GATEWAY_ENABLED", "0")
        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert settings.enabled is False

    def test_database_url_is_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_url is stored as SecretStr."""
        monkeypatch.setenv("MCP_GATEWAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert settings.database_url.get_secret_value() == "postgresql+asyncpg://u:p@h/d"

    def test_embedder_model_default(self) -> None:
        """embedder_model has a default value."""
        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert settings.embedder_model == "nvidia/llama-nemotron-embed-1b-v2"

    def test_nats_password_is_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """nats_password is stored as SecretStr."""
        monkeypatch.setenv("MCP_GATEWAY_NATS_PASSWORD", "nats-secret")
        settings = MCPGatewaySettings()  # type: ignore[call-arg]
        assert settings.nats_password.get_secret_value() == "nats-secret"


class TestGetSettings:
    """Tests for the get_settings singleton function."""

    def test_returns_settings_instance(self) -> None:
        """get_settings returns an MCPGatewaySettings instance."""
        settings = get_settings()
        assert isinstance(settings, MCPGatewaySettings)

    def test_singleton_behavior(self) -> None:
        """get_settings returns the same instance on subsequent calls."""
        first = get_settings()
        second = get_settings()
        assert first is second

    def test_singleton_reset(self) -> None:
        """reset_settings clears the singleton so next call creates a new one."""
        first = get_settings()
        reset_settings()
        second = get_settings()
        assert first is not second

    def test_env_override_after_reset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After reset, new settings pick up changed env vars."""
        settings1 = get_settings()
        assert settings1.mcp_port == 8100

        reset_settings()
        monkeypatch.setenv("MCP_GATEWAY_MCP_PORT", "9999")
        settings2 = get_settings()
        assert settings2.mcp_port == 9999
