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
        allow=[
            "read", "grep", "glob",
            "list_dir", "tree",
            "git_log", "git_diff", "git_status",
            "diff",
            "env_get", "which",
            "http_request",
        ],
        deny=[],
    ),
    "coding": ProfileDef(
        allow=[
            "read", "write", "grep", "glob",
            "edit",
            "list_dir", "tree", "mkdir", "move", "delete",
            "bash",
            "http_request",
            "git_*",
            "env_get", "which", "find_replace",
            "diff", "patch",
        ],
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
