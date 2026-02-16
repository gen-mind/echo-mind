"""
Edit tools for agent system.

Provides search-and-replace text editing with proper validation and error handling.
All tools follow FAANG principal engineer quality standards.
"""

import difflib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field


def create_edit_tool() -> Callable[..., str]:
    """
    Create tool for search-and-replace text editing.

    Returns:
        Callable that performs search-and-replace in files.
    """

    def edit(
        path: Annotated[str, Field(description="File path to edit")],
        old_string: Annotated[str, Field(description="Text to find and replace")],
        new_string: Annotated[str, Field(description="Replacement text")],
        replace_all: Annotated[
            bool, Field(description="Replace all occurrences (default: first only)")
        ] = False,
    ) -> str:
        """
        Search and replace text in a file.

        Args:
            path: File path to edit.
            old_string: Text to find.
            new_string: Text to replace with.
            replace_all: If True, replace all occurrences; otherwise only the first.

        Returns:
            Diff-style preview of changes or error message.
        """
        try:
            if not old_string:
                return "❌ Error: old_string cannot be empty"

            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return f"❌ Error: File not found: {path}"

            if not file_path.is_file():
                return f"❌ Error: Not a file: {path}"

            content = file_path.read_text(encoding="utf-8")

            if old_string not in content:
                return f"❌ Error: old_string not found in {path}"

            if old_string == new_string:
                return "❌ Error: old_string and new_string are identical"

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            # Write back
            file_path.write_text(new_content, encoding="utf-8")

            # Generate unified diff
            old_lines = content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
            diff_text = "".join(diff)

            return f"✅ Applied edit to {path}\n\n{diff_text}"

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except Exception as e:
            return f"❌ Error editing file: {str(e)}"

    return edit
