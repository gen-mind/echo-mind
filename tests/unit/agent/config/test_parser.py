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

    def test_invalid_config_type_raises_error(self, tmp_path):
        """Test that non-dict config raises error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- list\n- of\n- items")

        parser = ConfigParser(str(config_file))

        with pytest.raises(ValueError, match="expected dict"):
            parser.load()
