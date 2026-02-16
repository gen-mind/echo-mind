"""
Configuration for the sandbox runner process.

Loaded from environment variables injected by SandboxManager.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxRunnerSettings(BaseSettings):
    """Configuration for the agent sandbox runner."""

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file="/tmp/sandbox.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Identity (injected by SandboxManager on assignment)
    session_id: str = Field(
        default="",
        description="Unique session identifier assigned by SandboxManager",
    )
    user_id: str = Field(
        default="",
        description="User ID for this sandbox session",
    )
    mode: str = Field(
        default="warm",
        description="Container mode: 'warm' (waiting) or 'active' (processing)",
    )

    # Infrastructure
    nats_url: str = Field(
        default="nats://nats:4222",
        description="NATS server URL",
    )
    mcp_url: str = Field(
        default="http://mcp-gateway:8100",
        description="MCP Gateway URL for tool access",
    )

    # Health
    health_port: int = Field(
        default=8080,
        description="Port for health check endpoint",
    )

    # Agent
    llm_endpoint: str = Field(
        default="",
        description="LLM inference endpoint URL",
    )
    llm_model: str = Field(
        default="",
        description="LLM model name",
    )
    llm_api_key: str = Field(
        default="",
        description="LLM API key",
    )
