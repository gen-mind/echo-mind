"""
Sandbox agent runner -- Semantic Kernel agent with MCP tools.

Initializes a Semantic Kernel agent, connects to the MCP gateway for tools,
processes user queries, and yields streaming response tokens.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import nats
from nats.aio.client import Client as NATSClient

from sandbox.config import SandboxSettings

logger = logging.getLogger("echomind-sandbox")


@dataclass
class AgentMetrics:
    """Tracks per-session agent usage metrics.

    Attributes:
        message_count: Number of user messages processed.
        tool_calls_count: Number of MCP tool calls made.
        total_tokens: Estimated total LLM tokens consumed.
        error_count: Number of errors encountered.
    """

    message_count: int = 0
    tool_calls_count: int = 0
    total_tokens: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialize metrics to a dictionary.

        Returns:
            Dictionary with all metric fields.
        """
        return {
            "message_count": self.message_count,
            "tool_calls_count": self.tool_calls_count,
            "total_tokens": self.total_tokens,
            "error_count": self.error_count,
        }


@dataclass
class QueryContext:
    """Context for a single user query.

    Attributes:
        query: The user's input text.
        conversation_history: Prior messages for context.
        sources: Requested data sources / collections.
        metadata: Additional key-value metadata.
    """

    query: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRunner:
    """
    Runs a Semantic Kernel agent with MCP-provided tools.

    Responsibilities:
    - Initialize Semantic Kernel agent with LLM configuration
    - Connect to MCP gateway as tool source
    - Process incoming queries through the agent
    - Stream response tokens to NATS output subjects
    - Track usage metrics (messages, tool calls, tokens)

    The agent runner is stateful per session -- it maintains conversation
    history and MCP connection for the lifetime of the sandbox container.

    Attributes:
        metrics: Accumulated usage metrics for this session.
    """

    def __init__(self, settings: SandboxSettings, nc: NATSClient) -> None:
        """
        Initialize the agent runner.

        Args:
            settings: Sandbox configuration with LLM and MCP settings.
            nc: Connected NATS client for publishing responses.
        """
        self._settings = settings
        self._nc = nc
        self._initialized = False
        self.metrics = AgentMetrics()

        # Subjects for this session
        self._output_subject = f"sandbox.{settings.session_id}.output"
        self._stream_subject = f"sandbox.{settings.session_id}.stream"

    async def initialize(self) -> None:
        """
        Initialize the Semantic Kernel agent and MCP tool connection.

        Sets up:
        - LLM client (OpenAI/Anthropic/etc.) based on settings
        - MCP client connection to the gateway
        - Semantic Kernel kernel with registered plugins

        Raises:
            ConnectionError: If MCP gateway is unreachable.
            ValueError: If LLM configuration is invalid.
        """
        # TODO: Phase 5 -- Initialize Semantic Kernel
        # 1. Create SK kernel with LLM service:
        #    kernel = Kernel()
        #    kernel.add_service(OpenAIChatCompletion(
        #        ai_model_id=self._settings.llm_model,
        #        api_key=self._settings.llm_api_key,
        #        endpoint=self._settings.llm_endpoint,
        #    ))
        #
        # 2. Connect MCP client to gateway:
        #    mcp_client = MCPClient(
        #        url=self._settings.mcp_url,
        #        headers={"X-Sandbox-Session-Id": self._settings.session_id,
        #                 "X-Sandbox-User-Id": str(self._settings.user_id)},
        #    )
        #    tools = await mcp_client.list_tools()
        #    kernel.add_plugin(MCPPlugin(mcp_client, tools))
        #
        # 3. Create chat agent:
        #    self._agent = ChatCompletionAgent(
        #        kernel=kernel,
        #        instructions=self._settings.agent_instructions,
        #    )

        self._initialized = True
        logger.info(
            "🤖 Agent runner initialized (provider=%s, model=%s)",
            self._settings.llm_provider,
            self._settings.llm_model,
        )

    async def process_query(self, context: QueryContext) -> None:
        """
        Process a user query through the agent and publish results via NATS.

        Streams tokens to the ``stream`` subject and publishes the final
        complete response to the ``output`` subject.

        Args:
            context: The query context with user input and conversation history.

        Raises:
            RuntimeError: If agent runner is not initialized.
        """
        if not self._initialized:
            raise RuntimeError("Agent runner not initialized. Call initialize() first.")

        self.metrics.message_count += 1
        start_time = time.monotonic()

        logger.info(
            "🔍 Processing query (message #%d): %.80s...",
            self.metrics.message_count,
            context.query,
        )

        try:
            full_response = ""
            async for token in self._run_agent(context):
                full_response += token
                await self._publish_stream_token(token)

            elapsed = time.monotonic() - start_time
            await self._publish_complete(full_response)

            logger.info(
                "✅ Query processed (message #%d, %.2fs, %d tokens)",
                self.metrics.message_count,
                elapsed,
                self.metrics.total_tokens,
            )

        except Exception as e:
            self.metrics.error_count += 1
            logger.exception("❌ Query processing failed: %s", e)
            await self._publish_error(str(e))
            raise

    async def _run_agent(self, context: QueryContext) -> AsyncIterator[str]:
        """
        Execute the Semantic Kernel agent and yield response tokens.

        Args:
            context: Query context with user input.

        Yields:
            String tokens as the agent generates them.
        """
        # TODO: Phase 5 -- Implement Semantic Kernel agent execution
        # async for chunk in self._agent.invoke_stream(
        #     ChatHistory(messages=[
        #         *context.conversation_history,
        #         ChatMessageContent(role="user", content=context.query),
        #     ])
        # ):
        #     token = str(chunk)
        #     self.metrics.total_tokens += 1  # Approximate
        #     yield token

        # Skeleton: yield placeholder indicating agent is not yet wired
        yield f"[Agent skeleton] Received query: {context.query}"
        self.metrics.total_tokens += len(context.query.split())

    async def _publish_stream_token(self, token: str) -> None:
        """
        Publish a streaming token to NATS.

        Args:
            token: The text token to stream.
        """
        payload = json.dumps({"type": "token", "data": token}).encode("utf-8")
        await self._nc.publish(self._stream_subject, payload)

    async def _publish_complete(self, full_response: str) -> None:
        """
        Publish completion signal with full response to NATS.

        Args:
            full_response: The complete assembled response text.
        """
        payload = json.dumps({
            "type": "complete",
            "data": full_response,
            "metrics": self.metrics.to_dict(),
        }).encode("utf-8")
        await self._nc.publish(self._stream_subject, payload)

        # Also publish to output subject (final assembled response)
        output_payload = json.dumps({
            "type": "response",
            "content": full_response,
            "metrics": self.metrics.to_dict(),
        }).encode("utf-8")
        await self._nc.publish(self._output_subject, output_payload)

    async def _publish_error(self, error_message: str) -> None:
        """
        Publish an error event to NATS.

        Args:
            error_message: Human-readable error description.
        """
        payload = json.dumps({
            "type": "error",
            "error": error_message,
            "metrics": self.metrics.to_dict(),
        }).encode("utf-8")
        await self._nc.publish(self._stream_subject, payload)

    async def shutdown(self) -> None:
        """
        Clean up agent resources.

        Closes MCP client connection and releases any held resources.
        """
        # TODO: Phase 5 -- Close MCP client and SK kernel
        self._initialized = False
        logger.info(
            "🛑 Agent runner shut down (metrics: %s)",
            self.metrics.to_dict(),
        )
