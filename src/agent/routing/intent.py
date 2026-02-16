"""
LLM-based intent classifier for agent routing fallback.

When no binding matches, the intent classifier uses a lightweight LLM
to determine which agent best handles the incoming message based on
agent instructions/descriptions.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.config.schema import AgentConfig

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """Given the following agents, select the best one to handle this message.
Respond with ONLY the agent ID, nothing else.

Agents:
{agent_list}

Message: "{message}"
"""


class IntentClassifier:
    """
    Classifies user intent to select the best-matching agent.

    Uses an OpenAI-compatible API to send a classification prompt
    listing available agents and their instructions, then parses
    the response to extract the agent ID.

    Attributes:
        api_key: API key for the LLM service.
        model: Model identifier (default: gpt-4o-mini).
        base_url: Optional base URL for OpenAI-compatible API.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ) -> None:
        """
        Initialize intent classifier.

        Args:
            api_key: API key for LLM service.
            model: Model identifier for classification.
            base_url: Optional base URL for OpenAI-compatible API.
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        """
        Lazily initialize the OpenAI async client.

        Returns:
            AsyncOpenAI client instance.

        Raises:
            ImportError: If openai package is not installed.
        """
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as e:
                raise ImportError(
                    "openai package is required for intent classification. "
                    "Install with: pip install openai"
                ) from e

            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncOpenAI(**kwargs)

        return self._client

    async def classify(
        self, message: str, agents: list[AgentConfig]
    ) -> str | None:
        """
        Classify a message to find the best-matching agent.

        Args:
            message: User message text to classify.
            agents: Available agents to choose from.

        Returns:
            Agent ID of the best match, or None if classification fails.
        """
        if not agents:
            logger.warning("⚠️ No agents provided for intent classification")
            return None

        if not message or not message.strip():
            logger.warning("⚠️ Empty message for intent classification")
            return None

        agent_ids = {agent.id for agent in agents}
        prompt = self._build_prompt(message, agents)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.0,
            )

            raw_answer = response.choices[0].message.content.strip()
            result = self._parse_response(raw_answer, agent_ids)

            if result:
                logger.info(
                    "🎯 Intent classified: message→%s (raw: %s)",
                    result,
                    raw_answer,
                )
            else:
                logger.warning(
                    "⚠️ Intent classification returned unknown agent: %s",
                    raw_answer,
                )

            return result

        except Exception as e:
            logger.error("❌ Intent classification failed: %s", e)
            return None

    def _build_prompt(
        self, message: str, agents: list[AgentConfig]
    ) -> str:
        """
        Build the classification prompt.

        Args:
            message: User message to classify.
            agents: Available agents with instructions.

        Returns:
            Formatted prompt string.
        """
        agent_lines = []
        for agent in agents:
            instructions = agent.instructions or agent.name
            # Truncate long instructions for the prompt
            if len(instructions) > 200:
                instructions = instructions[:197] + "..."
            agent_lines.append(f"- {agent.id}: {instructions.strip()}")

        agent_list = "\n".join(agent_lines)
        return _CLASSIFICATION_PROMPT.format(
            agent_list=agent_list,
            message=message,
        )

    @staticmethod
    def _parse_response(
        raw_answer: str, valid_ids: set[str]
    ) -> str | None:
        """
        Parse the LLM response to extract a valid agent ID.

        Args:
            raw_answer: Raw text response from the LLM.
            valid_ids: Set of valid agent identifiers.

        Returns:
            Matched agent ID or None.
        """
        # Try exact match first
        cleaned = raw_answer.strip().lower()
        for agent_id in valid_ids:
            if cleaned == agent_id.lower():
                return agent_id

        # Try to find an agent ID anywhere in the response
        for agent_id in valid_ids:
            if agent_id.lower() in cleaned:
                return agent_id

        return None
