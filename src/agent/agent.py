"""
Basic Agent Wrapper for Microsoft Agent Framework.

This module provides a wrapper around the Microsoft Agent Framework that:
- Integrates with the configuration system
- Connects to OpenAI-compatible endpoints
- Registers tools from the ToolsRegistry
- Provides a simple interface for running agents
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from agent_framework import Agent, AgentSession
from agent_framework.openai import OpenAIChatClient
from pydantic import BaseModel, Field

from .config.schema import AgentConfig, MoltbotConfig
from .mcp.manager import MCPManager
from .policy.engine import ToolPolicyEngine
from .policy.middleware import ToolPolicyMiddleware
from .sessions.manager import SessionManager
from .sessions.provider import JSONLHistoryProvider
from .tools.middleware import PathRestrictionMiddleware
from .tools.registry import ToolsRegistry

logger = logging.getLogger(__name__)


class AgentRunRequest(BaseModel):
    """Request model for running an agent."""

    input: str = Field(..., description="User input message")
    stream: bool = Field(False, description="Enable streaming responses")
    session_key: str | None = Field(
        None, description="Session key for conversation state"
    )
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class AgentRunResponse(BaseModel):
    """Response model from agent execution."""

    output: str = Field(..., description="Agent response text")
    finish_reason: str | None = Field(None, description="Reason for completion")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Tools that were called"
    )
    usage: dict[str, int] | None = Field(None, description="Token usage statistics")


class BasicAgentWrapper:
    """
    Wrapper for Microsoft Agent Framework Agent.

    Provides a simple interface for creating and running agents with:
    - Configuration from AgentConfig
    - OpenAI-compatible endpoint support
    - Tool registration
    - Streaming and non-streaming execution
    """

    def __init__(
        self,
        config: AgentConfig,
        tools_registry: ToolsRegistry,
        api_key: str | None = None,
        base_url: str | None = None,
        global_config: MoltbotConfig | None = None,
        session_manager: SessionManager | None = None,
        max_messages: int | None = None,
        mcp_tools: list[Any] | None = None,
    ) -> None:
        """
        Initialize agent wrapper.

        Args:
            config: Agent configuration
            tools_registry: Registry of available tools
            api_key: OpenAI API key (or from env)
            base_url: OpenAI base URL (or from env)
            global_config: Root config for policy engine (optional)
            session_manager: Session manager for JSONL persistence (optional)
            max_messages: Max history messages to load per session (optional)
            mcp_tools: MCP tool instances from MCPManager (optional)

        Raises:
            ValueError: If API key is missing
        """
        self.config = config
        self.tools_registry = tools_registry
        self.global_config = global_config
        self.session_manager = session_manager
        self._mcp_tools = mcp_tools or []

        # Get API credentials
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "❌ OPENAI_API_KEY not found in environment or parameters"
            )

        # Get base URL (defaults to OpenAI)
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        # Create OpenAI client
        client_kwargs: dict[str, Any] = {
            "model_id": config.model,
            "api_key": self.api_key,
        }
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        logger.info(
            f"🤖 Creating OpenAI client for model '{config.model}' "
            f"(base_url: {self.base_url or 'default'})"
        )
        self.client = OpenAIChatClient(**client_kwargs)

        # Get tools
        self._tools = self._get_tools()

        # Apply approval overrides from config
        if global_config:
            self.tools_registry.apply_approval_overrides(global_config.approval)

        # Build middleware list
        middleware: list[Any] = []
        if global_config:
            self._policy_engine = ToolPolicyEngine(global_config, config)
            middleware.append(ToolPolicyMiddleware(self._policy_engine))
            logger.info(
                f"🔒 Policy middleware enabled for agent '{config.id}'"
            )

            # Add path restriction middleware if enabled
            path_cfg = global_config.sandbox.path_restriction
            if path_cfg.enabled:
                middleware.append(
                    PathRestrictionMiddleware(
                        allowed_paths=path_cfg.allowed_paths or None,
                        denied_paths=path_cfg.denied_paths or None,
                    )
                )
                logger.info(
                    f"🔒 Path restriction middleware enabled for agent '{config.id}'"
                )
        else:
            self._policy_engine = None

        # Build context providers (session history)
        context_providers: list[Any] = []
        if session_manager:
            history_provider = JSONLHistoryProvider(
                "history",
                session_manager,
                max_messages=max_messages,
            )
            context_providers.append(history_provider)
            logger.info(
                "📜 History provider enabled for agent '%s' "
                "(max_messages=%s)",
                config.id,
                max_messages,
            )

        # Combine native tools + MCP tools
        all_tools: list[Any] = list(self._tools) + list(self._mcp_tools)

        # Create agent
        agent_kwargs: dict[str, Any] = {
            "client": self.client,
            "id": config.id,
            "name": config.name,
            "instructions": config.instructions,
            "tools": all_tools if all_tools else None,
        }
        if middleware:
            agent_kwargs["middleware"] = middleware
        if context_providers:
            agent_kwargs["context_providers"] = context_providers

        self.agent = Agent(**agent_kwargs)

        logger.info(
            f"✅ Agent '{config.name}' initialized with "
            f"{len(self._tools)} native + {len(self._mcp_tools)} MCP tools"
        )

    def _get_tools(self) -> list[Any]:
        """
        Get all registered tools.

        When a policy engine is configured, runtime filtering is handled
        by ToolPolicyMiddleware — no pre-filtering here to avoid
        applying agent policy twice.

        Returns:
            List of all tool functions.
        """
        tools = self.tools_registry.get_all()
        logger.info(f"📦 Loaded {len(tools)} tools (runtime filtering via middleware)")
        return tools

    async def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """
        Run the agent with given input (non-streaming).

        Args:
            request: Agent run request

        Returns:
            Agent response

        Raises:
            RuntimeError: If agent execution fails
        """
        try:
            logger.info(f"🏃 Running agent '{self.config.name}' (non-streaming)")

            # Build session if session_key provided
            session = None
            if request.session_key:
                session = AgentSession(session_id=request.session_key)

            # Execute agent
            run_kwargs: dict[str, Any] = {}
            if session is not None:
                run_kwargs["session"] = session

            response = await self.agent.run(request.input, **run_kwargs)

            # Extract response text
            output = ""
            if hasattr(response, "content"):
                # Handle ChatResponse
                if isinstance(response.content, list):
                    # Multiple content items
                    output = " ".join(
                        str(item) for item in response.content if item
                    )
                else:
                    output = str(response.content) if response.content else ""
            else:
                output = str(response)

            # Extract metadata
            finish_reason = getattr(response, "finish_reason", None)
            usage_dict = None
            if hasattr(response, "usage") and response.usage:
                usage_dict = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(
                        response.usage, "completion_tokens", 0
                    ),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }

            logger.info(
                f"✅ Agent completed (finish_reason: {finish_reason}, "
                f"usage: {usage_dict})"
            )

            # Extract tool calls from response if available
            tool_calls_list: list[dict[str, Any]] = []
            raw_tool_calls = getattr(response, "tool_calls", None)
            if raw_tool_calls and isinstance(raw_tool_calls, (list, tuple)):
                for tc in raw_tool_calls:
                    tool_calls_list.append({
                        "id": getattr(tc, "id", None),
                        "name": getattr(tc, "name", None),
                        "arguments": getattr(tc, "arguments", {}),
                    })

            return AgentRunResponse(
                output=output,
                finish_reason=finish_reason,
                tool_calls=tool_calls_list,
                usage=usage_dict,
            )

        except Exception as e:
            logger.exception(f"❌ Agent execution failed: {e}")
            raise RuntimeError(f"Agent execution failed: {e}") from e

    async def run_stream(
        self, request: AgentRunRequest
    ) -> AsyncIterator[str]:
        """
        Run the agent with streaming responses.

        Uses Agent.run(stream=True) which returns a ResponseStream
        (async iterable of AgentResponseUpdate).

        Args:
            request: Agent run request

        Yields:
            Response chunks

        Raises:
            RuntimeError: If streaming fails
        """
        try:
            logger.info(f"🏃 Running agent '{self.config.name}' (streaming)")

            # Build session if session_key provided
            session = None
            if request.session_key:
                session = AgentSession(session_id=request.session_key)

            # Agent.run with stream=True returns a ResponseStream (async iterable)
            run_kwargs: dict[str, Any] = {"stream": True}
            if session is not None:
                run_kwargs["session"] = session

            response_stream = self.agent.run(request.input, **run_kwargs)

            async for chunk in response_stream:
                if hasattr(chunk, "content") and chunk.content:
                    # Handle AgentResponseUpdate
                    if isinstance(chunk.content, list):
                        for item in chunk.content:
                            if item:
                                yield str(item)
                    else:
                        yield str(chunk.content)
                elif chunk:
                    yield str(chunk)

            logger.info("✅ Streaming completed")

        except Exception as e:
            logger.exception(f"❌ Streaming failed: {e}")
            raise RuntimeError(f"Streaming failed: {e}") from e


class AgentFactory:
    """
    Factory for creating agent wrappers from configuration.

    Simplifies agent creation by handling common setup.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        global_config: MoltbotConfig | None = None,
        session_manager: SessionManager | None = None,
        max_messages: int | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        """
        Initialize factory.

        Args:
            api_key: Default OpenAI API key
            base_url: Default OpenAI base URL
            global_config: Root config for policy engine (optional)
            session_manager: Session manager for JSONL persistence (optional)
            max_messages: Max history messages to load per session (optional)
            mcp_manager: MCPManager for MCP server tools (optional)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.global_config = global_config
        self.session_manager = session_manager
        self.max_messages = max_messages
        self.mcp_manager = mcp_manager
        self.tools_registry = ToolsRegistry()

        logger.info(
            f"🏭 AgentFactory initialized with {self.tools_registry.count()} tools"
        )

    def create_agent(
        self,
        config: AgentConfig,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> BasicAgentWrapper:
        """
        Create an agent wrapper.

        Args:
            config: Agent configuration
            api_key: Override API key
            base_url: Override base URL

        Returns:
            Configured agent wrapper

        Raises:
            ValueError: If configuration is invalid
        """
        try:
            # Resolve MCP tools for this agent
            mcp_tools: list[Any] = []
            if self.mcp_manager and config.mcp_servers:
                mcp_tools = self.mcp_manager.get_tools_for_agent(
                    config.mcp_servers
                )

            agent = BasicAgentWrapper(
                config=config,
                tools_registry=self.tools_registry,
                api_key=api_key or self.api_key,
                base_url=base_url or self.base_url,
                global_config=self.global_config,
                session_manager=self.session_manager,
                max_messages=self.max_messages,
                mcp_tools=mcp_tools,
            )
            logger.info(f"✅ Created agent '{config.name}'")
            return agent
        except Exception as e:
            logger.exception(f"❌ Failed to create agent '{config.name}': {e}")
            raise ValueError(f"Failed to create agent: {e}") from e
