"""
Unit tests for provider detection.

Tests cover detection of OpenAI, Anthropic, and local providers
from model identifier strings, including case insensitivity.
Target: 100% code coverage.
"""

import pytest

from src.agent.policy.providers import detect_provider


class TestDetectProvider:
    """Tests for detect_provider function."""

    @pytest.mark.parametrize(
        "model,expected",
        [
            ("gpt-4o-mini", "openai"),
            ("gpt-3.5-turbo", "openai"),
            ("o1-preview", "openai"),
            ("o3-mini", "openai"),
        ],
        ids=["gpt-4o-mini", "gpt-3.5-turbo", "o1-preview", "o3-mini"],
    )
    def test_openai_models(self, model: str, expected: str) -> None:
        """Test OpenAI model detection for various model names."""
        assert detect_provider(model) == expected

    @pytest.mark.parametrize(
        "model,expected",
        [
            ("claude-3-sonnet", "anthropic"),
            ("claude-3-haiku", "anthropic"),
        ],
        ids=["claude-3-sonnet", "claude-3-haiku"],
    )
    def test_anthropic_models(self, model: str, expected: str) -> None:
        """Test Anthropic model detection for various model names."""
        assert detect_provider(model) == expected

    def test_case_insensitive_openai(self) -> None:
        """Test that OpenAI detection is case insensitive."""
        assert detect_provider("GPT-4o") == "openai"

    def test_case_insensitive_anthropic(self) -> None:
        """Test that Anthropic detection is case insensitive."""
        assert detect_provider("CLAUDE-3-OPUS") == "anthropic"

    @pytest.mark.parametrize(
        "model",
        ["llama-3.1-70b", "mistral-7b", ""],
        ids=["llama", "mistral", "empty-string"],
    )
    def test_local_fallback(self, model: str) -> None:
        """Test that unknown or empty models default to local."""
        assert detect_provider(model) == "local"
