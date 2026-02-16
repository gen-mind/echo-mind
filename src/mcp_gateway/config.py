"""
Configuration for the MCP Gateway Service.

Uses Pydantic Settings to load environment variables with MCP_GATEWAY_ prefix.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPGatewaySettings(BaseSettings):
    """Settings for the MCP Gateway service."""

    # Service Settings
    enabled: bool = Field(
        True,
        description="Enable MCP gateway",
    )
    health_port: int = Field(
        8080,
        description="Health check HTTP port",
    )
    mcp_port: int = Field(
        8100,
        description="MCP HTTP transport port",
    )

    # Logging
    log_level: str = Field(
        "INFO",
        description="Logging level",
    )

    # Qdrant
    qdrant_host: str = Field(
        "localhost",
        description="Qdrant host",
    )
    qdrant_port: int = Field(
        6333,
        description="Qdrant REST port",
    )
    qdrant_api_key: str | None = Field(
        None,
        description="Qdrant API key",
    )

    # Embedder gRPC
    embedder_host: str = Field(
        "localhost",
        description="Embedder gRPC host",
    )
    embedder_port: int = Field(
        50051,
        description="Embedder gRPC port",
    )
    embedder_timeout: float = Field(
        30.0,
        description="Embedder gRPC timeout in seconds",
    )

    # Skills
    skills_dir: str = Field(
        "/app/config/skills",
        description="Skills directory path",
    )
    skill_execution_timeout: int = Field(
        30,
        description="Max seconds for skill execution",
        gt=0,
    )
    skill_max_output_bytes: int = Field(
        65536,
        description="Max output size in bytes (64KB)",
        gt=0,
    )

    model_config = SettingsConfigDict(
        env_prefix="MCP_GATEWAY_",
        env_file=".env",
        extra="ignore",
    )


_settings: MCPGatewaySettings | None = None


def get_settings() -> MCPGatewaySettings:
    """
    Get MCP Gateway settings from environment.

    Returns:
        MCPGatewaySettings instance (singleton).
    """
    global _settings
    if _settings is None:
        _settings = MCPGatewaySettings()  # type: ignore[call-arg]
    return _settings


def reset_settings() -> None:
    """
    Reset settings singleton for testing.

    Allows tests to override environment variables and get fresh settings.
    """
    global _settings
    _settings = None
