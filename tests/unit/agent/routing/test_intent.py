"""
Unit tests for IntentClassifier.

Tests cover classification, response parsing, error handling,
and edge cases with mocked OpenAI client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.config.schema import AgentConfig
from agent.routing.intent import IntentClassifier


def _make_agent(
    agent_id: str, instructions: str = "A helpful agent"
) -> AgentConfig:
    """
    Create an AgentConfig for testing.

    Args:
        agent_id: Agent identifier.
        instructions: Agent instructions text.

    Returns:
        AgentConfig instance.
    """
    return AgentConfig(
        id=agent_id,
        name=agent_id.title(),
        model="gpt-4o-mini",
        instructions=instructions,
    )


def _mock_completion(content: str) -> MagicMock:
    """
    Build a mock ChatCompletion response.

    Args:
        content: The text content of the response.

    Returns:
        MagicMock mimicking openai ChatCompletion.
    """
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassify:
    """Tests for intent classification."""

    @pytest.mark.asyncio
    async def test_successful_classification(self) -> None:
        """Classifier returns correct agent_id on match."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("coder"), _make_agent("researcher")]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("coder")
        )
        classifier._client = mock_client

        result = await classifier.classify("Write some Python code", agents)
        assert result == "coder"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self) -> None:
        """Classifier returns None when LLM response doesn't match."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("coder"), _make_agent("researcher")]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("unknown_agent")
        )
        classifier._client = mock_client

        result = await classifier.classify("hello", agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_agents_returns_none(self) -> None:
        """Classifier returns None when no agents provided."""
        classifier = IntentClassifier(api_key="test-key")
        result = await classifier.classify("hello", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_message_returns_none(self) -> None:
        """Classifier returns None when message is empty."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("assistant")]
        result = await classifier.classify("", agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_message_returns_none(self) -> None:
        """Classifier returns None when message is only whitespace."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("assistant")]
        result = await classifier.classify("   ", agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self) -> None:
        """Classifier returns None on API error."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("assistant")]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        classifier._client = mock_client

        result = await classifier.classify("hello", agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_response(self) -> None:
        """Classifier matches agent_id case-insensitively."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("Coder")]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion("CODER")
        )
        classifier._client = mock_client

        result = await classifier.classify("code this", agents)
        assert result == "Coder"

    @pytest.mark.asyncio
    async def test_agent_id_in_longer_response(self) -> None:
        """Classifier finds agent_id embedded in longer response."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [_make_agent("coder"), _make_agent("researcher")]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_completion(
                "I think the best agent is coder for this task."
            )
        )
        classifier._client = mock_client

        result = await classifier.classify("Write some Python", agents)
        assert result == "coder"


# ---------------------------------------------------------------------------
# Prompt Building
# ---------------------------------------------------------------------------


class TestPromptBuilding:
    """Tests for classification prompt construction."""

    def test_prompt_includes_agents(self) -> None:
        """Prompt includes all agent IDs and instructions."""
        classifier = IntentClassifier(api_key="test-key")
        agents = [
            _make_agent("coder", "You write code"),
            _make_agent("researcher", "You do research"),
        ]
        prompt = classifier._build_prompt("hello", agents)
        assert "coder: You write code" in prompt
        assert "researcher: You do research" in prompt
        assert 'Message: "hello"' in prompt

    def test_long_instructions_truncated(self) -> None:
        """Instructions longer than 200 chars are truncated."""
        classifier = IntentClassifier(api_key="test-key")
        long_instructions = "x" * 300
        agents = [_make_agent("agent1", long_instructions)]
        prompt = classifier._build_prompt("test", agents)
        assert "..." in prompt
        assert len(prompt) < len(long_instructions) + 200


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    """Tests for LLM response parsing."""

    def test_exact_match(self) -> None:
        """Exact agent_id match works."""
        result = IntentClassifier._parse_response(
            "coder", {"coder", "researcher"}
        )
        assert result == "coder"

    def test_no_match(self) -> None:
        """Unknown response returns None."""
        result = IntentClassifier._parse_response(
            "unknown", {"coder", "researcher"}
        )
        assert result is None

    def test_partial_match(self) -> None:
        """Agent_id found within longer text."""
        result = IntentClassifier._parse_response(
            "I recommend coder", {"coder", "researcher"}
        )
        assert result == "coder"


# ---------------------------------------------------------------------------
# Client Initialization
# ---------------------------------------------------------------------------


class TestClientInit:
    """Tests for lazy client initialization."""

    def test_missing_openai_raises(self) -> None:
        """ImportError raised when openai not installed."""
        classifier = IntentClassifier(api_key="test-key")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai package"):
                classifier._get_client()

    def test_client_created_with_base_url(self) -> None:
        """Client is created with base_url when provided."""
        classifier = IntentClassifier(
            api_key="test-key",
            base_url="http://localhost:8000/v1",
        )
        mock_openai_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client_instance
        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            client = classifier._get_client()
            mock_openai_module.AsyncOpenAI.assert_called_once_with(
                api_key="test-key",
                base_url="http://localhost:8000/v1",
            )
            assert client is mock_client_instance

    def test_client_created_without_base_url(self) -> None:
        """Client is created without base_url when not provided."""
        classifier = IntentClassifier(api_key="test-key")
        mock_openai_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client_instance
        with patch.dict("sys.modules", {"openai": mock_openai_module}):
            client = classifier._get_client()
            mock_openai_module.AsyncOpenAI.assert_called_once_with(
                api_key="test-key",
            )

    def test_client_cached(self) -> None:
        """Client is lazily created and cached."""
        classifier = IntentClassifier(api_key="test-key")
        mock_client = MagicMock()
        classifier._client = mock_client
        assert classifier._get_client() is mock_client
