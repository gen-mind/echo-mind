"""
Configuration Parser for Agent System

Loads YAML configuration files and converts them to typed Python objects.
Supports environment variable expansion using ${VAR} or ${VAR:-default} syntax.

Confidence: High - Parser follows Moltbot pattern exactly
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    AgentConfig,
    MoltbotConfig,
    RouteBindingConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)


class ConfigParser:
    """
    YAML configuration parser with environment variable expansion.

    Usage:
        parser = ConfigParser("config/agents/config.yaml")
        config = parser.load()
    """

    def __init__(self, config_path: str) -> None:
        """
        Initialize parser with configuration file path.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}"
            )

    def load(self) -> MoltbotConfig:
        """
        Load and parse configuration file.

        Returns:
            Parsed and validated configuration

        Raises:
            yaml.YAMLError: If YAML parsing fails
            ValueError: If configuration is invalid
        """
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        if not isinstance(raw_config, dict):
            raise ValueError(
                f"Invalid configuration: expected dict, got {type(raw_config)}"
            )

        # Expand environment variables
        expanded = self._expand_env_vars(raw_config)

        # Parse into structured config
        config = self._parse_config(expanded)

        return config

    def _expand_env_vars(self, config: Any) -> Any:
        """
        Recursively expand ${ENV_VAR} and ${ENV_VAR:-default} placeholders.

        Args:
            config: Configuration value (can be dict, list, str, etc.)

        Returns:
            Configuration with environment variables expanded
        """

        def expand_value(value: Any) -> Any:
            if isinstance(value, str):
                # Match ${ENV_VAR} or ${ENV_VAR:-default}
                pattern = r"\$\{([^}:]+)(?::-(.*))?\}"

                def replacer(match: re.Match[str]) -> str:
                    env_var = match.group(1)
                    default = match.group(2) or ""
                    return os.getenv(env_var, default)

                return re.sub(pattern, replacer, value)
            elif isinstance(value, dict):
                return {k: expand_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [expand_value(v) for v in value]
            else:
                return value

        return expand_value(config)

    def _parse_config(self, raw: dict[str, Any]) -> MoltbotConfig:
        """
        Parse raw dictionary into MoltbotConfig.

        Args:
            raw: Raw configuration dictionary

        Returns:
            Validated configuration object

        Raises:
            ValueError: If configuration is invalid
        """
        # Parse agents
        agents_raw = raw.get("agents", {}).get("list", [])
        if not agents_raw:
            raise ValueError("No agents defined in configuration")

        agents = [
            AgentConfig(
                id=a["id"],
                name=a["name"],
                model=a["model"],
                instructions=a.get("instructions"),
                tools=self._parse_tool_policy(a.get("tools", {})),
                dm_scope=a.get("dmScope", "per-peer"),
            )
            for a in agents_raw
        ]

        # Parse routing
        routing_raw = raw.get("routing", {})
        routing = RoutingConfig(
            defaults=routing_raw.get("defaults", {}),
            bindings=[
                RouteBindingConfig(
                    match=b["match"],
                    agent_id=b["agentId"],
                )
                for b in routing_raw.get("bindings", [])
            ],
        )

        # Parse global tools
        tools = self._parse_tool_policy(raw.get("tools", {}))

        # Parse sandbox
        sandbox_raw = raw.get("sandbox", {})
        sandbox = SandboxConfig(
            enabled=sandbox_raw.get("enabled", False),
            safe_bins=sandbox_raw.get("safeBins", []),
            path_prepend=sandbox_raw.get("pathPrepend"),
            denied_tools=sandbox_raw.get("deniedTools", []),
            subagent_denied_tools=sandbox_raw.get(
                "subagentDeniedTools",
                ["write", "bash", "git_add", "git_commit"],
            ),
        )

        return MoltbotConfig(
            agents=agents,
            routing=routing,
            tools=tools,
            sandbox=sandbox,
        )

    def _parse_tool_policy(self, raw: dict[str, Any]) -> ToolPolicy:
        """
        Parse tool policy from dictionary.

        Args:
            raw: Raw tool policy dictionary

        Returns:
            Parsed tool policy object
        """
        by_provider = {}
        for provider, policy_raw in raw.get("byProvider", {}).items():
            by_provider[provider] = self._parse_tool_policy(policy_raw)

        return ToolPolicy(
            profile=raw.get("profile"),
            allow=raw.get("allow", []),
            deny=raw.get("deny", []),
            by_provider=by_provider,
        )
