"""
Tool Policy Middleware for Agent Framework.

ChatMiddleware that applies the 8-layer policy filter before each LLM call,
ensuring agents only see tools they are allowed to use.
"""

import logging
from typing import Any

from agent_framework import ChatContext, ChatMiddleware

from .engine import PolicyContext, ToolPolicyEngine

logger = logging.getLogger(__name__)


class ToolPolicyMiddleware(ChatMiddleware):
    """
    Middleware that applies 9-layer policy filtering before each LLM call.

    Intercepts the tool list in ``context.options`` and replaces it with
    the filtered set from ToolPolicyEngine.
    """

    def __init__(self, engine: ToolPolicyEngine) -> None:
        """
        Initialize middleware with a policy engine.

        Args:
            engine: Configured ToolPolicyEngine instance.
        """
        self.engine = engine

    async def process(self, context: ChatContext, call_next: Any) -> None:
        """
        Filter tools before passing to the LLM.

        Args:
            context: Chat context containing options with tools.
            call_next: Callable to invoke the next middleware or LLM.
        """
        tools = context.options.get("tools", [])

        policy_ctx = PolicyContext(
            provider=self.engine.provider,
            parent_agent_id=(
                context.metadata.get("parent_agent_id")
                if context.metadata
                else None
            ),
        )

        filtered = self.engine.filter_tools(tools, policy_ctx)
        context.options["tools"] = filtered

        logger.debug(
            f"🔒 ToolPolicyMiddleware: {len(tools)} → {len(filtered)} tools"
        )

        await call_next()
