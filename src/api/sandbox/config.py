"""
Sandbox service configuration using Pydantic Settings.

All configuration is loaded from environment variables with SANDBOX_ prefix.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    """Configuration for sandbox container management."""

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Feature flag
    enabled: bool = Field(
        default=False,
        description="Enable sandbox container management (opt-in via SANDBOX_ENABLED=true)",
    )

    # Pool management
    pool_size: int = Field(
        default=3,
        ge=0,
        le=50,
        description="Number of warm containers to maintain in the pool",
    )
    max_instances: int = Field(
        default=15,
        ge=1,
        le=100,
        description="Hard cap on total sandbox containers (warm + active)",
    )

    # Timeouts
    idle_timeout: int = Field(
        default=300,
        ge=60,
        description="Warm container idle TTL in seconds before destruction",
    )
    session_timeout: int = Field(
        default=3600,
        ge=60,
        description="Maximum session duration in seconds",
    )

    # Container settings
    image: str = Field(
        default="gsantopaolo/echomind-agent-sandbox:0.1.0-beta.1",
        description="Docker image for sandbox containers",
    )
    network: str = Field(
        default="sandbox",
        description="Docker network for sandbox containers",
    )
    cpu_limit: float = Field(
        default=2.0,
        gt=0,
        description="CPU limit per sandbox container",
    )
    memory_limit: str = Field(
        default="2g",
        description="Memory limit per sandbox container",
    )

    # Infrastructure
    reconciliation_interval: int = Field(
        default=30,
        ge=5,
        description="Interval in seconds between reconciliation loop runs",
    )
    nats_url: str = Field(
        default="nats://nats:4222",
        description="NATS server URL for sandbox communication",
    )
    mcp_url: str = Field(
        default="http://mcp-gateway:8100",
        description="MCP Gateway URL for sandbox tool access",
    )


@lru_cache
def get_sandbox_settings() -> SandboxSettings:
    """Get cached sandbox settings instance.

    Returns:
        Singleton SandboxSettings loaded from environment variables.
    """
    return SandboxSettings()
