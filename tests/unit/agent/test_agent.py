"""
Unit tests for agent wrapper.

Tests cover agent creation, configuration, tool registration, and execution.
Target: 100% code coverage
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agent.agent import (
    AgentFactory,
    AgentRunRequest,
    AgentRunResponse,
    BasicAgentWrapper,
)
from src.agent.config.schema import AgentConfig, ToolPolicy
from src.agent.tools.registry import ToolsRegistry


class TestAgentRunRequest:
    """Tests for AgentRunRequest model."""

    def test_minimal_request(self):
        """Test creating minimal request."""
        request = AgentRunRequest(input="Hello")
        assert request.input == "Hello"
        assert request.stream is False
        assert request.context == {}

    def test_full_request(self):
        """Test creating full request."""
        request = AgentRunRequest(
            input="Test query",
            stream=True,
            context={"user_id": 123},
        )
        assert request.input == "Test query"
        assert request.stream is True
        assert request.context == {"user_id": 123}


class TestAgentRunResponse:
    """Tests for AgentRunResponse model."""

    def test_minimal_response(self):
        """Test creating minimal response."""
        response = AgentRunResponse(output="Hello!")
        assert response.output == "Hello!"
        assert response.finish_reason is None
        assert response.tool_calls == []
        assert response.usage is None

    def test_full_response(self):
        """Test creating full response."""
        response = AgentRunResponse(
            output="Response text",
            finish_reason="stop",
            tool_calls=[{"name": "read", "args": {"path": "file.txt"}}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        assert response.output == "Response text"
        assert response.finish_reason == "stop"
        assert len(response.tool_calls) == 1
        assert response.usage["total_tokens"] == 30


class TestBasicAgentWrapper:
    """Tests for BasicAgentWrapper class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock agent config."""
        return AgentConfig(
            id="test-agent",
            name="Test Agent",
            model="gpt-4o-mini",
            instructions="You are a test assistant.",
        )

    @pytest.fixture
    def mock_tools_registry(self):
        """Create mock tools registry."""
        registry = Mock(spec=ToolsRegistry)
        registry.get_all.return_value = []
        registry.count.return_value = 0
        return registry

    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    def test_initialization_success(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test successful initialization."""
        # Mock the client
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock the agent
        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent

        # Create wrapper
        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
            base_url="https://test.example.com",
        )

        # Verify client created correctly
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args.kwargs
        assert call_kwargs["model_id"] == "gpt-4o-mini"
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["base_url"] == "https://test.example.com"

        # Verify agent created correctly
        mock_agent_class.assert_called_once()
        call_kwargs = mock_agent_class.call_args.kwargs
        assert call_kwargs["id"] == "test-agent"
        assert call_kwargs["name"] == "Test Agent"
        assert call_kwargs["instructions"] == "You are a test assistant."

        # Verify wrapper state
        assert wrapper.config == mock_config
        assert wrapper.api_key == "test-key"
        assert wrapper.base_url == "https://test.example.com"

    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    def test_initialization_from_env(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry, monkeypatch
    ):
        """Test initialization with credentials from environment."""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com")

        # Mock classes
        mock_client_class.return_value = Mock()
        mock_agent_class.return_value = Mock()

        # Create wrapper (no explicit credentials)
        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
        )

        # Verify credentials from env
        assert wrapper.api_key == "env-key"
        assert wrapper.base_url == "https://env.example.com"

        # Verify client used env values
        call_kwargs = mock_client_class.call_args.kwargs
        assert call_kwargs["api_key"] == "env-key"
        assert call_kwargs["base_url"] == "https://env.example.com"

    def test_initialization_missing_api_key(self, mock_config, mock_tools_registry, monkeypatch):
        """Test that missing API key raises error."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
            BasicAgentWrapper(
                config=mock_config,
                tools_registry=mock_tools_registry,
            )

    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    def test_get_tools_no_policy(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test tool retrieval with no policy (all tools)."""
        mock_client_class.return_value = Mock()
        mock_agent_class.return_value = Mock()

        # Mock registry to return tools
        mock_tools = [Mock(name="tool1"), Mock(name="tool2")]
        mock_tools_registry.get_all.return_value = mock_tools

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Verify all tools retrieved
        mock_tools_registry.get_all.assert_called_once()
        assert wrapper._tools == mock_tools

    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    def test_get_tools_always_loads_all(
        self, mock_agent_class, mock_client_class, mock_tools_registry
    ):
        """Test that _get_tools always loads all tools (middleware handles filtering)."""
        mock_client_class.return_value = Mock()
        mock_agent_class.return_value = Mock()

        # Config with tool policy — but _get_tools ignores it now
        config = AgentConfig(
            id="test",
            name="Test",
            model="gpt-4o-mini",
            tools=ToolPolicy(allow=["read*"], deny=["write*"]),
        )

        mock_tools = [Mock(name="read"), Mock(name="write")]
        mock_tools_registry.get_all.return_value = mock_tools

        wrapper = BasicAgentWrapper(
            config=config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Should call get_all (not get_filtered) — middleware handles runtime filtering
        mock_tools_registry.get_all.assert_called()
        assert wrapper._tools == mock_tools

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_success(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test successful agent run."""
        mock_client_class.return_value = Mock()

        # Mock agent response
        mock_response = Mock()
        mock_response.content = "Agent response"
        mock_response.finish_reason = "stop"
        mock_response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_response)
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Run agent
        request = AgentRunRequest(input="Test query")
        response = await wrapper.run(request)

        # Verify response
        assert response.output == "Agent response"
        assert response.finish_reason == "stop"
        assert response.usage["total_tokens"] == 30

        # Verify agent was called
        mock_agent.run.assert_called_once_with("Test query")

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_response_without_content_attr(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test agent run when response has no .content attribute."""
        mock_client_class.return_value = Mock()

        # Simple object with no .content attribute
        class PlainResponse:
            def __str__(self) -> str:
                return "plain string response"

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=PlainResponse())
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        request = AgentRunRequest(input="Test")
        response = await wrapper.run(request)

        assert response.output == "plain string response"

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_with_list_content(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test agent run with list content response."""
        mock_client_class.return_value = Mock()

        # Mock agent response with list content
        mock_response = Mock()
        mock_response.content = ["Part 1", " Part 2"]
        mock_response.finish_reason = "stop"
        mock_response.usage = None

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_response)
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Run agent
        request = AgentRunRequest(input="Test")
        response = await wrapper.run(request)

        # Verify response joined
        assert response.output == "Part 1  Part 2"

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_failure(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test agent run with error."""
        mock_client_class.return_value = Mock()

        # Mock agent to raise error
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=Exception("API error"))
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Verify exception raised
        request = AgentRunRequest(input="Test")
        with pytest.raises(RuntimeError, match="Agent execution failed"):
            await wrapper.run(request)

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_stream_success(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test successful streaming run."""
        mock_client_class.return_value = Mock()

        # Agent.run(input, stream=True) returns a sync object with __aiter__
        class MockResponseStream:
            async def __aiter__(self):
                chunks = [
                    Mock(content="Hello"),
                    Mock(content=" world"),
                    Mock(content="!"),
                ]
                for chunk in chunks:
                    yield chunk

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=MockResponseStream())
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Collect streamed chunks
        request = AgentRunRequest(input="Test", stream=True)
        chunks = []
        async for chunk in wrapper.run_stream(request):
            chunks.append(chunk)

        # Verify chunks
        assert chunks == ["Hello", " world", "!"]
        mock_agent.run.assert_called_once_with("Test", stream=True)

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_stream_with_list_content(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test streaming with list content."""
        mock_client_class.return_value = Mock()

        # Agent.run(input, stream=True) returns a sync object with __aiter__
        class MockResponseStream:
            async def __aiter__(self):
                yield Mock(content=["Multi", "part"])
                yield Mock(content=["chunk"])

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=MockResponseStream())
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Collect chunks
        request = AgentRunRequest(input="Test", stream=True)
        chunks = []
        async for chunk in wrapper.run_stream(request):
            chunks.append(chunk)

        # Verify all parts yielded
        assert chunks == ["Multi", "part", "chunk"]

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_stream_chunk_without_content(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test streaming with chunk that has no .content but is truthy."""
        mock_client_class.return_value = Mock()

        class RawChunk:
            """Chunk with no .content attribute."""
            def __str__(self) -> str:
                return "raw-chunk"

        class MockResponseStream:
            async def __aiter__(self):
                yield RawChunk()

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=MockResponseStream())
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        request = AgentRunRequest(input="Test", stream=True)
        chunks = []
        async for chunk in wrapper.run_stream(request):
            chunks.append(chunk)

        assert chunks == ["raw-chunk"]

    @pytest.mark.asyncio
    @patch("src.agent.agent.OpenAIChatClient")
    @patch("src.agent.agent.Agent")
    async def test_run_stream_failure(
        self, mock_agent_class, mock_client_class, mock_config, mock_tools_registry
    ):
        """Test streaming with error."""
        mock_client_class.return_value = Mock()

        # Agent.run raises when called
        mock_agent = Mock()
        mock_agent.run = Mock(side_effect=Exception("Streaming error"))
        mock_agent_class.return_value = mock_agent

        wrapper = BasicAgentWrapper(
            config=mock_config,
            tools_registry=mock_tools_registry,
            api_key="test-key",
        )

        # Verify exception raised
        request = AgentRunRequest(input="Test", stream=True)
        with pytest.raises(RuntimeError, match="Streaming failed"):
            async for _ in wrapper.run_stream(request):
                pass


class TestAgentFactory:
    """Tests for AgentFactory class."""

    @patch("src.agent.agent.ToolsRegistry")
    def test_initialization(self, mock_registry_class):
        """Test factory initialization."""
        mock_registry = Mock()
        mock_registry.count.return_value = 10
        mock_registry_class.return_value = mock_registry

        factory = AgentFactory(
            api_key="factory-key",
            base_url="https://factory.example.com",
        )

        assert factory.api_key == "factory-key"
        assert factory.base_url == "https://factory.example.com"
        mock_registry_class.assert_called_once()

    @patch("src.agent.agent.BasicAgentWrapper")
    @patch("src.agent.agent.ToolsRegistry")
    def test_create_agent_success(self, mock_registry_class, mock_wrapper_class):
        """Test successful agent creation."""
        mock_registry_class.return_value = Mock(count=Mock(return_value=5))
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper

        factory = AgentFactory(api_key="factory-key")

        config = AgentConfig(
            id="test",
            name="Test",
            model="gpt-4o-mini",
        )

        # Create agent
        agent = factory.create_agent(config)

        # Verify wrapper created
        mock_wrapper_class.assert_called_once()
        call_kwargs = mock_wrapper_class.call_args.kwargs
        assert call_kwargs["config"] == config
        assert call_kwargs["api_key"] == "factory-key"
        assert agent == mock_wrapper

    @patch("src.agent.agent.BasicAgentWrapper")
    @patch("src.agent.agent.ToolsRegistry")
    def test_create_agent_with_override(self, mock_registry_class, mock_wrapper_class):
        """Test agent creation with credential override."""
        mock_registry_class.return_value = Mock(count=Mock(return_value=5))
        mock_wrapper_class.return_value = Mock()

        factory = AgentFactory(api_key="factory-key", base_url="https://factory.com")

        config = AgentConfig(id="test", name="Test", model="gpt-4o-mini")

        # Create with override
        factory.create_agent(
            config,
            api_key="override-key",
            base_url="https://override.com",
        )

        # Verify override used
        call_kwargs = mock_wrapper_class.call_args.kwargs
        assert call_kwargs["api_key"] == "override-key"
        assert call_kwargs["base_url"] == "https://override.com"

    @patch("src.agent.agent.BasicAgentWrapper")
    @patch("src.agent.agent.ToolsRegistry")
    def test_create_agent_failure(self, mock_registry_class, mock_wrapper_class):
        """Test agent creation with error."""
        mock_registry_class.return_value = Mock(count=Mock(return_value=5))
        mock_wrapper_class.side_effect = Exception("Creation error")

        factory = AgentFactory(api_key="factory-key")

        config = AgentConfig(id="test", name="Test", model="gpt-4o-mini")

        # Verify exception raised
        with pytest.raises(ValueError, match="Failed to create agent"):
            factory.create_agent(config)
