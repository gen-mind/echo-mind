"""
Provider Detection for Tool Policy.

Detects the LLM provider from a model identifier string and provides
provider-specific default policies.
"""


def detect_provider(model: str) -> str:
    """
    Detect LLM provider from model name.

    Args:
        model: Model identifier (e.g., "gpt-4o-mini", "claude-3-sonnet").

    Returns:
        Provider name: "openai", "anthropic", or "local".
    """
    lower = model.lower()
    if lower.startswith(("gpt-", "o1-", "o3-")):
        return "openai"
    if lower.startswith("claude-"):
        return "anthropic"
    return "local"
