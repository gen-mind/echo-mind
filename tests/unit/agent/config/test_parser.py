"""
Unit tests for configuration parser.

Tests cover YAML parsing, environment variable expansion, and error cases.
Target: 100% code coverage
"""

import os

import pytest
import yaml

from src.agent.config.parser import ConfigParser
from src.agent.config.schema import MoltbotConfig


class TestConfigParser:
    """Tests for ConfigParser class."""

    def test_file_not_found(self):
        """Test that missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ConfigParser("nonexistent.yaml")

    def test_minimal_config(self, tmp_path):
        """Test parsing minimal valid config."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools:
  profile: full

sandbox:
  enabled: false
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert isinstance(config, MoltbotConfig)
        assert len(config.agents) == 1
        assert config.agents[0].id == "assistant"
        assert config.routing.defaults["agentId"] == "assistant"

    def test_complete_config(self, tmp_path):
        """Test parsing complete config with all fields."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"
      instructions: "You are helpful"
      dmScope: "per-peer"
      tools:
        profile: full
        allow: ["*"]
        deny: ["system_*"]

    - id: coder
      name: "Coder"
      model: "gpt-4o"
      tools:
        profile: coding
        allow: ["read*", "write*", "git_*"]

routing:
  defaults:
    agentId: assistant
  bindings:
    - match:
        channel: test
      agentId: coder

tools:
  profile: full
  allow: ["*"]
  deny: ["admin_*"]
  byProvider:
    anthropic:
      deny: ["sessions_spawn"]

sandbox:
  enabled: true
  safeBins: ["git", "ls"]
  pathPrepend: "/usr/bin"
  deniedTools: ["exec"]
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert len(config.agents) == 2
        assert config.agents[0].instructions == "You are helpful"
        assert config.agents[1].tools.profile == "coding"
        assert len(config.routing.bindings) == 1
        assert config.tools.deny == ["admin_*"]
        assert "anthropic" in config.tools.by_provider
        assert config.sandbox.enabled is True

    def test_env_var_expansion(self, tmp_path):
        """Test environment variable expansion."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "${TEST_MODEL}"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        # Set environment variable
        os.environ["TEST_MODEL"] = "gpt-4o-test"

        try:
            parser = ConfigParser(str(config_file))
            config = parser.load()

            assert config.agents[0].model == "gpt-4o-test"
        finally:
            del os.environ["TEST_MODEL"]

    def test_env_var_with_default(self, tmp_path):
        """Test environment variable expansion with default value."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "${NONEXISTENT_VAR:-gpt-4o-mini}"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.agents[0].model == "gpt-4o-mini"

    def test_invalid_yaml_raises_error(self, tmp_path):
        """Test that invalid YAML raises error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: syntax:")

        parser = ConfigParser(str(config_file))

        with pytest.raises(yaml.YAMLError):
            parser.load()

    def test_missing_agents_raises_error(self, tmp_path):
        """Test that missing agents section raises error."""
        config_yaml = """
routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))

        with pytest.raises(ValueError, match="No agents defined"):
            parser.load()

    def test_approval_config_parsing(self, tmp_path):
        """Test parsing approval section from config."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

approval:
  requireApproval:
    - "bash"
    - "git_push"
  skipApproval:
    - "write"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.approval.require_approval == ["bash", "git_push"]
        assert config.approval.skip_approval == ["write"]

    def test_approval_config_defaults(self, tmp_path):
        """Test that missing approval section uses defaults."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.approval.require_approval == []
        assert config.approval.skip_approval == []

    def test_path_restriction_parsing(self, tmp_path):
        """Test parsing pathRestriction inside sandbox section."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}

sandbox:
  enabled: true
  pathRestriction:
    enabled: true
    allowedPaths:
      - "/project"
      - "/tmp"
    deniedPaths:
      - "/etc"
      - "~/.ssh"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.sandbox.path_restriction.enabled is True
        assert config.sandbox.path_restriction.allowed_paths == ["/project", "/tmp"]
        assert config.sandbox.path_restriction.denied_paths == ["/etc", "~/.ssh"]

    def test_path_restriction_defaults(self, tmp_path):
        """Test that missing pathRestriction uses defaults."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox:
  enabled: false
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.sandbox.path_restriction.enabled is False
        assert config.sandbox.path_restriction.allowed_paths == []
        assert config.sandbox.path_restriction.denied_paths == []

    def test_invalid_config_type_raises_error(self, tmp_path):
        """Test that non-dict config raises error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- list\n- of\n- items")

        parser = ConfigParser(str(config_file))

        with pytest.raises(ValueError, match="expected dict"):
            parser.load()


class TestMCPServerParsing:
    """Tests for MCP server configuration parsing."""

    def test_parse_stdio_server(self, tmp_path):
        """Test parsing a stdio MCP server with all fields."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"
      mcpServers: ["filesystem"]

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env:
      NODE_ENV: production
    approvalMode: never_require
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert len(config.mcp_servers) == 1
        mcp = config.mcp_servers[0]
        assert mcp.name == "filesystem"
        assert mcp.transport == "stdio"
        assert mcp.command == "npx"
        assert mcp.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert mcp.env == {"NODE_ENV": "production"}
        assert mcp.approval_mode == "never_require"

        # Verify agent references
        assert config.agents[0].mcp_servers == ["filesystem"]

    def test_parse_http_server_with_headers(self, tmp_path):
        """Test parsing an HTTP MCP server with headers and env var expansion."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - name: github
    transport: http
    url: "https://mcp.example.com/github"
    headers:
      Authorization: "Bearer ${TEST_MCP_TOKEN:-default_token}"
    approvalMode: always_require
    toolApprovals:
      list_repos: never_require
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert len(config.mcp_servers) == 1
        mcp = config.mcp_servers[0]
        assert mcp.name == "github"
        assert mcp.transport == "http"
        assert mcp.url == "https://mcp.example.com/github"
        assert mcp.headers == {"Authorization": "Bearer default_token"}
        assert mcp.approval_mode == "always_require"
        assert mcp.tool_approvals == {"list_repos": "never_require"}

    def test_parse_agent_mcp_references(self, tmp_path):
        """Test parsing agent mcpServers references."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"
      mcpServers: ["fs", "github"]

    - id: researcher
      name: "Researcher"
      model: "gpt-4o-mini"
      mcpServers: ["fs"]

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - name: fs
    transport: stdio
    command: echo
  - name: github
    transport: http
    url: "https://test.com"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.agents[0].mcp_servers == ["fs", "github"]
        assert config.agents[1].mcp_servers == ["fs"]

    def test_backward_compat_no_mcp_section(self, tmp_path):
        """Test backward compatibility when mcpServers section is absent."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.mcp_servers == []
        assert config.agents[0].mcp_servers == []

    def test_empty_mcp_servers_list(self, tmp_path):
        """Test parsing with empty mcpServers list."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}
mcpServers: []
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        assert config.mcp_servers == []

    def test_parse_mcp_server_with_all_optional_fields(self, tmp_path):
        """Test parsing MCP server with requestTimeout and allowedTools."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - name: restricted
    transport: stdio
    command: npx
    args: ["-y", "server"]
    allowedTools: ["read_file", "list_dir"]
    requestTimeout: 60
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))
        config = parser.load()

        mcp = config.mcp_servers[0]
        assert mcp.allowed_tools == ["read_file", "list_dir"]
        assert mcp.request_timeout == 60

    def test_parse_mcp_server_missing_name_raises(self, tmp_path):
        """Test that MCP server without name raises ValueError."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - transport: stdio
    command: echo
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))

        with pytest.raises(ValueError, match="missing required field 'name'"):
            parser.load()

    def test_parse_mcp_server_missing_transport_raises(self, tmp_path):
        """Test that MCP server without transport raises ValueError."""
        config_yaml = """
agents:
  list:
    - id: assistant
      name: "Assistant"
      model: "gpt-4o-mini"

routing:
  defaults:
    agentId: assistant

tools: {}
sandbox: {}

mcpServers:
  - name: bad
    command: echo
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        parser = ConfigParser(str(config_file))

        with pytest.raises(ValueError, match="missing required field 'transport'"):
            parser.load()
