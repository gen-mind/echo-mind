"""
MCP Integration Showcase — end-to-end examples of the MCP subsystem.

This file is *documentation-by-example*. Each test class walks through a
real-world scenario so future developers can see how the pieces fit:

    Config (YAML)  →  MCPServerConfig  →  MCPManager  →  AgentFactory  →  Agent

All external dependencies (MCP servers, LLM clients, agent framework) are
mocked. These tests verify *wiring*, not protocol correctness.
"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.agent.agent import AgentFactory, BasicAgentWrapper
from src.agent.config.parser import ConfigParser
from src.agent.config.schema import (
    AgentConfig,
    MCPServerConfig,
    MoltbotConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)
from src.agent.mcp.manager import MCPManager
from src.agent.policy.engine import ToolPolicyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_global_config(
    agents: list[AgentConfig] | None = None,
    mcp_servers: list[MCPServerConfig] | None = None,
    tools: ToolPolicy | None = None,
) -> MoltbotConfig:
    """Build a minimal MoltbotConfig for tests.

    Args:
        agents: Agent configs (defaults to one basic agent).
        mcp_servers: MCP server configs (defaults to empty).
        tools: Global tool policy (defaults to profile=full).

    Returns:
        A valid MoltbotConfig.
    """
    default_agent = AgentConfig(
        id="assistant",
        name="Assistant",
        model="gpt-4o-mini",
    )
    resolved_agents = agents or [default_agent]
    # Route to the first agent by default (avoids ID mismatch)
    default_agent_id = resolved_agents[0].id
    return MoltbotConfig(
        agents=resolved_agents,
        routing=RoutingConfig(defaults={"agentId": default_agent_id}),
        tools=tools or ToolPolicy(profile="full"),
        sandbox=SandboxConfig(),
        mcp_servers=mcp_servers or [],
    )


def _make_function_tool(name: str) -> MagicMock:
    """Create a mock FunctionTool with the given name.

    Args:
        name: Tool name (used by policy engine for filtering).

    Returns:
        Mock with a .name attribute.
    """
    tool = MagicMock()
    tool.name = name
    return tool


# ===========================================================================
# Scenario A: Full config → MCPManager → AgentFactory flow
# ===========================================================================


class TestFullMCPFlow:
    """Demonstrates the complete wiring from config to agent creation.

    Flow:
        1. Define MCP server configs (stdio + http).
        2. Create MCPManager and connect servers.
        3. Pass manager into AgentFactory.
        4. Factory resolves MCP tools per agent via mcp_servers list.
        5. Agent is created with native + MCP tools combined.
    """

    @pytest.mark.asyncio
    async def test_config_to_agent_with_mcp_tools(self) -> None:
        """Full flow: MCP configs → manager → factory → agent with MCP tools."""

        # --- Step 1: Define MCP server configs ---
        filesystem_server = MCPServerConfig(
            name="filesystem",
            transport="stdio",
            command="npx",
            args=["-y", "@anthropic/mcp-filesystem", "/workspace"],
        )
        github_server = MCPServerConfig(
            name="github",
            transport="http",
            url="https://mcp.example.com/github",
            headers={"Authorization": "Bearer gh-token-123"},
        )

        # --- Step 2: Define an agent that uses both MCP servers ---
        agent_config = AgentConfig(
            id="coder",
            name="Coding Agent",
            model="gpt-4o-mini",
            instructions="You are a coding assistant.",
            mcp_servers=["filesystem", "github"],  # References MCP servers by name
        )

        global_config = _minimal_global_config(
            agents=[agent_config],
            mcp_servers=[filesystem_server, github_server],
        )

        # --- Step 3: Connect MCP servers via MCPManager ---
        mock_fs_tool = AsyncMock()
        mock_gh_tool = AsyncMock()

        with (
            patch("src.agent.mcp.manager.MCPStdioTool", return_value=mock_fs_tool),
            patch("src.agent.mcp.manager.MCPStreamableHTTPTool", return_value=mock_gh_tool),
        ):
            async with MCPManager(global_config.mcp_servers) as manager:
                # Both servers should be connected
                assert manager.is_connected("filesystem"), "filesystem server should connect"
                assert manager.is_connected("github"), "github server should connect"

                # --- Step 4: AgentFactory resolves MCP tools per agent ---
                with (
                    patch("src.agent.agent.OpenAIChatClient"),
                    patch("src.agent.agent.Agent") as mock_agent_cls,
                ):
                    factory = AgentFactory(
                        api_key="test-key",
                        global_config=global_config,
                        mcp_manager=manager,
                    )
                    wrapper = factory.create_agent(agent_config)

                    # --- Step 5: Verify agent was created with MCP tools ---
                    agent_call = mock_agent_cls.call_args
                    created_tools = agent_call.kwargs.get("tools", [])

                    # Should contain native tools + 2 MCP tools
                    assert mock_fs_tool in created_tools, (
                        "Filesystem MCP tool should be in agent's tool list"
                    )
                    assert mock_gh_tool in created_tools, (
                        "GitHub MCP tool should be in agent's tool list"
                    )

        # After exiting context manager, servers are disconnected
        mock_fs_tool.__aexit__.assert_called_once()
        mock_gh_tool.__aexit__.assert_called_once()


# ===========================================================================
# Scenario B: MCP tools coexist with native tools under policy filtering
# ===========================================================================


class TestMCPWithPolicyFiltering:
    """Shows how MCP tools and native tools are both subject to policy.

    The ToolPolicyEngine applies allow/deny filters to ALL tools — native
    function tools and MCP tool instances alike. MCP tools that don't match
    the policy are excluded just like native ones.
    """

    def test_policy_filters_mcp_alongside_native_tools(self) -> None:
        """Policy engine filters MCP + native tools uniformly."""

        # Native tools
        read_tool = _make_function_tool("read")
        write_tool = _make_function_tool("write")
        bash_tool = _make_function_tool("bash")

        # MCP tools (they also have a .name attribute)
        mcp_git_tool = _make_function_tool("mcp__github__create_pr")
        mcp_fs_tool = _make_function_tool("mcp__filesystem__read_file")

        all_tools = [read_tool, write_tool, bash_tool, mcp_git_tool, mcp_fs_tool]

        # Agent policy: deny bash and any mcp github tools
        agent_config = AgentConfig(
            id="restricted",
            name="Restricted Agent",
            model="gpt-4o-mini",
            tools=ToolPolicy(
                deny=["bash", "mcp__github__*"],
            ),
        )

        global_config = _minimal_global_config(
            agents=[agent_config],
            tools=ToolPolicy(profile="full"),
        )

        engine = ToolPolicyEngine(global_config, agent_config)
        filtered = engine.filter_tools(all_tools)

        # bash and mcp__github__create_pr should be denied
        filtered_names = [t.name for t in filtered]
        assert "read" in filtered_names, "read tool should pass policy"
        assert "write" in filtered_names, "write tool should pass policy"
        assert "mcp__filesystem__read_file" in filtered_names, (
            "MCP filesystem tool should pass policy"
        )
        assert "bash" not in filtered_names, "bash should be denied by policy"
        assert "mcp__github__create_pr" not in filtered_names, (
            "MCP github tool should be denied by wildcard pattern"
        )


# ===========================================================================
# Scenario C: Partial MCP server failure — graceful degradation
# ===========================================================================


class TestPartialMCPFailure:
    """Demonstrates graceful degradation when some MCP servers fail.

    MCPManager.connect_all() catches per-server errors. The agent still
    gets tools from servers that succeeded. Failed servers are logged
    as warnings, not exceptions.
    """

    @pytest.mark.asyncio
    async def test_one_server_fails_other_succeeds(self) -> None:
        """Agent gets tools from healthy server; failed server is skipped."""

        healthy_config = MCPServerConfig(
            name="healthy-fs",
            transport="stdio",
            command="npx",
            args=["server-fs"],
        )
        broken_config = MCPServerConfig(
            name="broken-api",
            transport="http",
            url="https://unreachable.example.com/mcp",
        )

        agent_config = AgentConfig(
            id="resilient",
            name="Resilient Agent",
            model="gpt-4o-mini",
            mcp_servers=["healthy-fs", "broken-api"],
        )

        # Mock: healthy server connects, broken server raises on __aenter__
        mock_healthy = AsyncMock()
        mock_broken = AsyncMock()
        mock_broken.__aenter__.side_effect = ConnectionError(
            "Connection refused: unreachable.example.com"
        )

        with (
            patch("src.agent.mcp.manager.MCPStdioTool", return_value=mock_healthy),
            patch("src.agent.mcp.manager.MCPStreamableHTTPTool", return_value=mock_broken),
        ):
            async with MCPManager([healthy_config, broken_config]) as manager:
                # Only healthy server should be connected
                assert manager.is_connected("healthy-fs"), (
                    "Healthy server should connect successfully"
                )
                assert not manager.is_connected("broken-api"), (
                    "Broken server should NOT be connected"
                )
                assert manager.connected_count == 1, (
                    "Only 1 of 2 servers should be connected"
                )

                # get_tools_for_agent still returns healthy tools
                tools = manager.get_tools_for_agent(["healthy-fs", "broken-api"])
                assert len(tools) == 1, (
                    "Should return tools only from the healthy server"
                )
                assert tools[0] is mock_healthy, (
                    "Returned tool should be the healthy server's tool"
                )

    @pytest.mark.asyncio
    async def test_all_servers_fail_agent_still_works(self) -> None:
        """Agent can still be created even if all MCP servers fail."""

        failing_config = MCPServerConfig(
            name="unavailable",
            transport="stdio",
            command="nonexistent-binary",
        )

        agent_config = AgentConfig(
            id="standalone",
            name="Standalone Agent",
            model="gpt-4o-mini",
            mcp_servers=["unavailable"],
        )

        global_config = _minimal_global_config(
            agents=[agent_config],
            mcp_servers=[failing_config],
        )

        mock_tool = AsyncMock()
        mock_tool.__aenter__.side_effect = FileNotFoundError("binary not found")

        with patch("src.agent.mcp.manager.MCPStdioTool", return_value=mock_tool):
            async with MCPManager(global_config.mcp_servers) as manager:
                assert manager.connected_count == 0, (
                    "No servers connected when all fail"
                )

                # Factory can still create agent — MCP tools list is simply empty
                with (
                    patch("src.agent.agent.OpenAIChatClient"),
                    patch("src.agent.agent.Agent") as mock_agent_cls,
                ):
                    factory = AgentFactory(
                        api_key="test-key",
                        global_config=global_config,
                        mcp_manager=manager,
                    )
                    wrapper = factory.create_agent(agent_config)

                    # Agent created with only native tools (no MCP)
                    agent_call = mock_agent_cls.call_args
                    created_tools = agent_call.kwargs.get("tools", [])

                    # No MCP tools in the list
                    assert mock_tool not in created_tools, (
                        "Failed MCP tool should NOT appear in agent's tools"
                    )


# ===========================================================================
# Scenario D: Config-driven setup from YAML
# ===========================================================================


class TestYAMLConfigToMCPSetup:
    """Demonstrates the YAML → parse → MCPManager → agent pipeline.

    This is the closest to production usage: a YAML config file defines
    MCP servers and agents, ConfigParser produces MoltbotConfig, and
    MCPManager + AgentFactory wire everything together.
    """

    @pytest.mark.asyncio
    async def test_yaml_config_drives_mcp_setup(self, tmp_path) -> None:
        """Parse YAML config → create MCPManager → create agent with MCP tools."""

        # --- Step 1: Write a realistic YAML config ---
        config_yaml = textwrap.dedent("""\
            agents:
              list:
                - id: assistant
                  name: Main Assistant
                  model: gpt-4o-mini
                  instructions: You help with coding tasks.
                  mcpServers:
                    - filesystem
                - id: researcher
                  name: Research Agent
                  model: gpt-4o-mini
                  instructions: You search the web.
                  mcpServers: []

            routing:
              defaults:
                agentId: assistant

            tools:
              profile: full

            sandbox:
              enabled: false

            mcpServers:
              - name: filesystem
                transport: stdio
                command: npx
                args:
                  - "-y"
                  - "@anthropic/mcp-filesystem"
                  - "/workspace"
                allowedTools:
                  - read_file
                  - list_directory
                requestTimeout: 30
        """)

        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        # --- Step 2: Parse config ---
        parser = ConfigParser(str(config_file))
        config = parser.load()

        # Verify MCP servers parsed correctly
        assert len(config.mcp_servers) == 1, "Should have 1 MCP server from YAML"
        fs_server = config.mcp_servers[0]
        assert fs_server.name == "filesystem", "Server name from YAML"
        assert fs_server.transport == "stdio", "Transport from YAML"
        assert fs_server.command == "npx", "Command from YAML"
        assert fs_server.allowed_tools == ["read_file", "list_directory"], (
            "Allowed tools from YAML"
        )
        assert fs_server.request_timeout == 30, "Timeout from YAML"

        # Verify agent references MCP server
        assistant = config.get_agent("assistant")
        assert assistant is not None, "assistant agent should exist"
        assert assistant.mcp_servers == ["filesystem"], (
            "Agent should reference filesystem MCP server"
        )

        # researcher has no MCP servers
        researcher = config.get_agent("researcher")
        assert researcher is not None, "researcher agent should exist"
        assert researcher.mcp_servers == [], "Researcher should have no MCP servers"

        # --- Step 3: Connect MCP servers ---
        mock_fs_tool = AsyncMock()
        with patch("src.agent.mcp.manager.MCPStdioTool", return_value=mock_fs_tool):
            async with MCPManager(config.mcp_servers) as manager:
                assert manager.is_connected("filesystem"), (
                    "Filesystem server should connect"
                )

                # --- Step 4: Create agents via factory ---
                with (
                    patch("src.agent.agent.OpenAIChatClient"),
                    patch("src.agent.agent.Agent") as mock_agent_cls,
                ):
                    factory = AgentFactory(
                        api_key="test-key",
                        global_config=config,
                        mcp_manager=manager,
                    )

                    # Assistant gets filesystem MCP tool
                    assistant_wrapper = factory.create_agent(assistant)
                    assistant_call = mock_agent_cls.call_args
                    assistant_tools = assistant_call.kwargs.get("tools", [])
                    assert mock_fs_tool in assistant_tools, (
                        "Assistant should get filesystem MCP tool"
                    )

                    # Reset mock to capture researcher's Agent() call
                    mock_agent_cls.reset_mock()

                    # Researcher gets NO MCP tools
                    researcher_wrapper = factory.create_agent(researcher)
                    researcher_call = mock_agent_cls.call_args
                    researcher_tools = researcher_call.kwargs.get("tools", [])
                    assert mock_fs_tool not in researcher_tools, (
                        "Researcher should NOT get filesystem MCP tool"
                    )
