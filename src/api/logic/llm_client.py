"""
LLM provider client for chat completion.

Supports multiple providers (OpenAI, Anthropic, Ollama, TGI/vLLM)
with streaming token generation.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from api.logic.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM configuration from database."""

    provider: str
    endpoint: str
    model_id: str
    api_key: str | None
    max_tokens: int
    temperature: float


@dataclass
class ChatMessage:
    """Chat message for LLM context."""

    role: str
    content: str


class LLMClient:
    """
    Async HTTP client for LLM providers.

    Supports:
    - OpenAI (and compatible APIs like Azure, Anyscale)
    - Anthropic
    - Ollama
    - TGI/vLLM (OpenAI-compatible)

    Attributes:
        timeout: HTTP request timeout in seconds.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        """
        Initialize LLM client.

        Args:
            timeout: Request timeout in seconds.
        """
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
            )
        return self._client

    async def stream_completion(
        self,
        config: LLMConfig,
        messages: list[ChatMessage],
    ) -> AsyncIterator[str]:
        """
        Stream chat completion tokens from LLM.

        Args:
            config: LLM configuration.
            messages: Chat messages for context.

        Yields:
            String tokens as they are generated.

        Raises:
            ServiceUnavailableError: If LLM service fails.
        """
        provider = config.provider.lower()

        if provider in ("openai", "tgi", "vllm", "ollama"):
            async for token in self._stream_openai_compatible(config, messages):
                yield token
        elif provider == "anthropic":
            async for token in self._stream_anthropic(config, messages):
                yield token
        else:
            logger.error("❌ Unsupported LLM provider: %s", provider)
            raise ServiceUnavailableError(f"LLM provider '{provider}'")

    async def _stream_openai_compatible(
        self,
        config: LLMConfig,
        messages: list[ChatMessage],
    ) -> AsyncIterator[str]:
        """
        Stream from OpenAI-compatible API.

        Works with: OpenAI, Azure OpenAI, TGI, vLLM, Ollama.
        """
        client = await self._ensure_client()

        # Build endpoint URL
        endpoint = config.endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/v1/chat/completions"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        payload = {
            "model": config.model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "stream": True,
        }

        logger.info(
            "🤖 Streaming from %s (%s)",
            config.provider,
            config.model_id,
        )

        try:
            async with client.stream(
                "POST",
                endpoint,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(
                        "❌ LLM API error %d: %s",
                        response.status_code,
                        error_body.decode()[:500],
                    )
                    raise ServiceUnavailableError(f"LLM ({config.provider})")

                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPError as e:
            logger.error("❌ HTTP error calling LLM: %s", e)
            raise ServiceUnavailableError(f"LLM ({config.provider})") from e

    async def _stream_anthropic(
        self,
        config: LLMConfig,
        messages: list[ChatMessage],
    ) -> AsyncIterator[str]:
        """Stream from Anthropic API."""
        client = await self._ensure_client()

        endpoint = config.endpoint.rstrip("/")
        if not endpoint.endswith("/messages"):
            endpoint = f"{endpoint}/v1/messages"

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if config.api_key:
            headers["x-api-key"] = config.api_key

        # Convert messages to Anthropic format
        system_message = ""
        anthropic_messages = []
        for m in messages:
            if m.role == "system":
                system_message = m.content
            else:
                anthropic_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": config.model_id,
            "messages": anthropic_messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "stream": True,
        }
        if system_message:
            payload["system"] = system_message

        logger.info("🤖 Streaming from Anthropic (%s)", config.model_id)

        try:
            async with client.stream(
                "POST",
                endpoint,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(
                        "❌ Anthropic API error %d: %s",
                        response.status_code,
                        error_body.decode()[:500],
                    )
                    raise ServiceUnavailableError("LLM (anthropic)")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                text = delta.get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPError as e:
            logger.error("❌ HTTP error calling Anthropic: %s", e)
            raise ServiceUnavailableError("LLM (anthropic)") from e

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("✅ LLM client closed")


# Global client instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def close_llm_client() -> None:
    """Close the global LLM client."""
    global _llm_client
    if _llm_client is not None:
        await _llm_client.close()
        _llm_client = None
