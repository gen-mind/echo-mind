"""
Policy Engine for Agent Tool Filtering.

Provides a 9-layer cascading policy system (Layer 7 skipped) that controls
which tools are available to each agent at runtime. Layers are applied in
order, each narrowing the set of available tools.

Layers:
    1. Profile (minimal/coding/messaging/full presets)
    2. Provider Profile (Anthropic/OpenAI quirks from global byProvider)
    3. Global Policy (config-wide allow/deny)
    4. Global + Provider (merged)
    5. Agent Policy (agent-specific allow/deny)
    6. Agent + Provider (merged)
    7. Group/Channel (SKIPPED — not implemented)
    8. Sandbox (denied_tools enforcement)
    9. Subagent (configurable restricted tools for spawned sub-agents)
"""

from .engine import PolicyContext, ToolPolicyEngine
from .middleware import ToolPolicyMiddleware
from .profiles import PROFILES
from .providers import detect_provider

__all__ = [
    "PolicyContext",
    "PROFILES",
    "ToolPolicyEngine",
    "ToolPolicyMiddleware",
    "detect_provider",
]
