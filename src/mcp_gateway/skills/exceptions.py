"""Domain exceptions for MCP Gateway skill execution."""


class SkillNotFoundError(Exception):
    """Raised when a skill is not found in the registry."""


class SkillTimeoutError(Exception):
    """Raised when skill execution exceeds timeout."""


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""
