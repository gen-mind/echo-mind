"""
Profile Presets for Tool Policy.

Named presets that define standard tool access patterns.
Each profile maps to an allow/deny list pair.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileDef:
    """
    Definition of a tool access profile.

    Attributes:
        allow: Tool name patterns to allow (empty = allow all).
        deny: Tool name patterns to deny (takes precedence over allow).
    """

    allow: list[str]
    deny: list[str]


PROFILES: dict[str, ProfileDef] = {
    "minimal": ProfileDef(
        allow=["read", "grep", "glob", "git_log", "git_diff", "git_status"],
        deny=[],
    ),
    "coding": ProfileDef(
        allow=["read", "write", "grep", "glob", "bash", "git_*"],
        deny=[],
    ),
    "messaging": ProfileDef(
        allow=[],
        deny=["*"],
    ),
    "full": ProfileDef(
        allow=["*"],
        deny=[],
    ),
}
