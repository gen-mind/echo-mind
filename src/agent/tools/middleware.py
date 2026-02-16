"""
Tool middleware for agent system.

Provides security middleware for tool invocations, including path restrictions.
"""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent_framework import FunctionInvocationContext, FunctionMiddleware

logger = logging.getLogger(__name__)

# Field names that are treated as file/directory paths
_PATH_FIELD_NAMES = {
    "path",
    "file_path",
    "directory",
    "source",
    "destination",
    "target",
    "file_a",
    "file_b",
}


class PathRestrictionMiddleware(FunctionMiddleware):
    """
    Enforces path restrictions on tool invocations.

    Checks arguments of tool calls for path-like fields and validates them
    against allowed/denied path lists.

    Args:
        allowed_paths: If set, paths must be under one of these directories.
        denied_paths: Paths under these directories are always blocked.
    """

    def __init__(
        self,
        allowed_paths: list[str] | None = None,
        denied_paths: list[str] | None = None,
    ) -> None:
        """
        Initialize path restriction middleware.

        Args:
            allowed_paths: If set, only paths under these directories are allowed.
            denied_paths: Paths under these directories are always blocked.
        """
        self._allowed_paths: list[Path] | None = (
            [Path(p).expanduser().resolve() for p in allowed_paths]
            if allowed_paths
            else None
        )
        self._denied_paths: list[Path] = (
            [Path(p).expanduser().resolve() for p in denied_paths]
            if denied_paths
            else []
        )

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """
        Validate path arguments against allowed/denied restrictions.

        Extracts path-like arguments from the invocation context and checks
        them against the configured restrictions. Blocked paths set an error
        result and skip execution.

        Args:
            context: Function invocation context with arguments.
            call_next: Callable to invoke the next middleware or function.
        """
        arguments = context.arguments

        for field_name in type(arguments).model_fields:
            if field_name not in _PATH_FIELD_NAMES:
                continue

            value = getattr(arguments, field_name, None)
            if not value or not isinstance(value, str):
                continue

            resolved = Path(value).expanduser().resolve()

            # Check denied paths first (always blocked)
            for denied in self._denied_paths:
                if _is_relative_to(resolved, denied):
                    logger.warning(
                        f"🚫 Path '{value}' blocked by denied path restriction"
                    )
                    context.result = (
                        f"❌ Error: Path '{value}' is not allowed "
                        f"(blocked by path restrictions)"
                    )
                    return

            # Check allowed paths (if set, path must be under one)
            if self._allowed_paths is not None:
                if not any(
                    _is_relative_to(resolved, allowed)
                    for allowed in self._allowed_paths
                ):
                    logger.warning(
                        f"🚫 Path '{value}' blocked: not under any allowed path"
                    )
                    context.result = (
                        f"❌ Error: Path '{value}' is not allowed "
                        f"(blocked by path restrictions)"
                    )
                    return

        await call_next()


def _is_relative_to(path: Path, parent: Path) -> bool:
    """
    Check if path is relative to parent directory.

    Uses Path.is_relative_to for Python 3.9+.

    Args:
        path: Path to check.
        parent: Parent directory to check against.

    Returns:
        True if path is under parent directory.
    """
    return path.is_relative_to(parent)
