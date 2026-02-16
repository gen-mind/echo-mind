"""
Sandbox agent configuration.

All settings are injected via environment variables by the SandboxManager
when the container is created or assigned to a session.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    """
    Configuration for the sandbox agent process.

    Environment variables are prefixed with ``SANDBOX_`` and injected
    by the SandboxManager at container creation/assignment time.

    Attributes:
        nats_url: NATS server URL for message bus communication.
        mcp_url: MCP gateway HTTP URL for tool access.
        session_id: Unique session identifier (routing key).
        user_id: Owner user ID for this session.
        mode: Container mode -- ``warm`` (idle, waiting) or ``active`` (processing).
        llm_provider: LLM provider name (openai, anthropic, etc.).
        llm_model: LLM model identifier.
        llm_api_key: LLM API key (decrypted at runtime).
        llm_endpoint: LLM API base URL.
        agent_instructions: System prompt / agent personality.
        max_turns: Maximum agent turns per query.
        timeout_seconds: Per-query timeout in seconds.
        log_level: Python logging level.
        health_port: HTTP port for health/readiness probes.
        heartbeat_interval: Seconds between heartbeat publishes.
    """

    nats_url: str = Field(
        "nats://nats:4222",
        description="NATS server URL",
    )
    mcp_url: str = Field(
        "http://mcp-server:8080",
        description="MCP gateway HTTP URL",
    )
    session_id: str = Field(
        "",
        description="Unique session identifier (injected by SandboxManager)",
    )
    user_id: int = Field(
        0,
        description="Owner user ID (injected by SandboxManager)",
    )
    mode: str = Field(
        "warm",
        description="Container mode: 'warm' (idle) or 'active' (processing)",
    )
    llm_provider: str = Field(
        "openai",
        description="LLM provider name",
    )
    llm_model: str = Field(
        "gpt-4o",
        description="LLM model identifier",
    )
    llm_api_key: str = Field(
        "",
        description="LLM API key",
    )
    llm_endpoint: str = Field(
        "https://api.openai.com/v1",
        description="LLM API base URL",
    )
    agent_instructions: str = Field(
        "You are EchoMind Assistant.",
        description="Agent system prompt / personality",
    )
    max_turns: int = Field(
        50,
        description="Maximum agent turns per query",
    )
    timeout_seconds: int = Field(
        300,
        description="Per-query timeout in seconds",
    )
    log_level: str = Field(
        "INFO",
        description="Python logging level",
    )
    health_port: int = Field(
        8080,
        description="HTTP port for health/readiness probes",
    )
    heartbeat_interval: int = Field(
        15,
        description="Seconds between heartbeat publishes",
    )

    model_config = SettingsConfigDict(env_prefix="SANDBOX_")
