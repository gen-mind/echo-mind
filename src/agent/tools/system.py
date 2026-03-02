"""
System tools for agent system.

Provides environment inspection, command lookup, and find-replace capabilities.
All tools follow FAANG principal engineer quality standards.
"""

import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field


_SENSITIVE_VAR_PATTERNS = {"password", "secret", "token", "api_key", "private_key"}


def create_env_get_tool() -> Callable[..., str]:
    """
    Create tool for getting environment variable values.

    Returns:
        Callable that retrieves environment variable values safely.
    """

    def env_get(
        name: Annotated[str, Field(description="Environment variable name")],
    ) -> str:
        """
        Get the value of an environment variable.

        Args:
            name: Environment variable name.

        Returns:
            Variable value or error message.
        """
        # Block sensitive variables
        name_lower = name.lower()
        for pattern in _SENSITIVE_VAR_PATTERNS:
            if pattern in name_lower:
                return f"❌ Error: Access to sensitive environment variable '{name}' is blocked"

        value = os.environ.get(name)
        if value is None:
            return f"❌ Error: Environment variable '{name}' not set"

        return value

    return env_get


def create_which_tool() -> Callable[..., str]:
    """
    Create tool for finding executables in PATH.

    Returns:
        Callable that finds executable paths.
    """

    def which(
        command: Annotated[str, Field(description="Command name to find")],
    ) -> str:
        """
        Find the full path of an executable in PATH.

        Args:
            command: Command name to look up.

        Returns:
            Full path to executable or error message.
        """
        result = shutil.which(command)
        if result is None:
            return f"❌ Error: Command '{command}' not found in PATH"

        return result

    return which


def create_find_replace_tool() -> Callable[..., str]:
    """
    Create tool for regex find-and-replace across files.

    Returns:
        Callable that performs find-and-replace operations.
    """

    _MAX_FILES = 100

    def find_replace(
        pattern: Annotated[str, Field(description="Regex pattern to find")],
        replacement: Annotated[str, Field(description="Replacement string")],
        path: Annotated[
            str, Field(description="Base directory to search")
        ] = ".",
        glob_pattern: Annotated[
            str, Field(description="File glob pattern")
        ] = "**/*",
        dry_run: Annotated[
            bool, Field(description="If True, show changes without writing")
        ] = True,
    ) -> str:
        """
        Find and replace text across files using regex.

        Args:
            pattern: Regular expression pattern to search for.
            replacement: Replacement string (supports regex backreferences).
            path: Base directory to search in.
            glob_pattern: Glob pattern to filter files.
            dry_run: If True, only show what would change.

        Returns:
            Summary of modified files or error message.
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"❌ Error: Invalid regex pattern: {str(e)}"

        try:
            base_path = Path(path).expanduser().resolve()

            if not base_path.exists():
                return f"❌ Error: Directory not found: {path}"

            if not base_path.is_dir():
                return f"❌ Error: Not a directory: {path}"

            # Collect matching files (skip directories)
            all_files = sorted(
                f for f in base_path.glob(glob_pattern) if f.is_file()
            )

            if len(all_files) > _MAX_FILES:
                return (
                    f"❌ Error: Too many files ({len(all_files)}). "
                    f"Maximum is {_MAX_FILES}. Use a more specific glob pattern."
                )

            modified_files: list[str] = []
            results: list[str] = []

            for file_path in all_files:
                # Skip binary files
                try:
                    content = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue

                new_content = regex.sub(replacement, content)

                if new_content != content:
                    rel_path = str(file_path.relative_to(base_path))
                    match_count = len(regex.findall(content))
                    modified_files.append(rel_path)

                    if dry_run:
                        results.append(
                            f"  {rel_path}: {match_count} match(es) would be replaced"
                        )
                    else:
                        file_path.write_text(new_content, encoding="utf-8")
                        results.append(
                            f"  {rel_path}: {match_count} match(es) replaced"
                        )

            if not modified_files:
                return f"No matches found for pattern: {pattern}"

            mode = "Would modify" if dry_run else "Modified"
            header = f"{'[DRY RUN] ' if dry_run else ''}✅ {mode} {len(modified_files)} file(s):\n"
            return header + "\n".join(results)

        except Exception as e:
            return f"❌ Error: {str(e)}"

    return find_replace
