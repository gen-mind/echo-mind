"""
Text tools for agent system.

Provides diff and patch capabilities for file comparison and modification.
All tools follow FAANG principal engineer quality standards.
"""

import difflib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field


def create_diff_tool() -> Callable[..., str]:
    """
    Create tool for comparing two files.

    Returns:
        Callable that generates unified diffs between two files.
    """

    def diff(
        file_a: Annotated[str, Field(description="Path to first file")],
        file_b: Annotated[str, Field(description="Path to second file")],
        context_lines: Annotated[
            int, Field(description="Number of context lines around changes", ge=0, le=20)
        ] = 3,
    ) -> str:
        """
        Compare two files and show unified diff.

        Args:
            file_a: Path to the first file.
            file_b: Path to the second file.
            context_lines: Number of context lines around changes.

        Returns:
            Unified diff output or error message.
        """
        try:
            path_a = Path(file_a).expanduser().resolve()
            path_b = Path(file_b).expanduser().resolve()

            if not path_a.exists():
                return f"❌ Error: File not found: {file_a}"

            if not path_b.exists():
                return f"❌ Error: File not found: {file_b}"

            if not path_a.is_file():
                return f"❌ Error: Not a file: {file_a}"

            if not path_b.is_file():
                return f"❌ Error: Not a file: {file_b}"

            lines_a = path_a.read_text(encoding="utf-8").splitlines(keepends=True)
            lines_b = path_b.read_text(encoding="utf-8").splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    lines_a,
                    lines_b,
                    fromfile=file_a,
                    tofile=file_b,
                    n=context_lines,
                )
            )

            if not diff_lines:
                return "(files are identical)"

            return "".join(diff_lines)

        except PermissionError:
            return f"❌ Error: Permission denied"
        except UnicodeDecodeError:
            return f"❌ Error: One or both files are not valid UTF-8 text"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return diff


def create_patch_tool() -> Callable[..., str]:
    """
    Create tool for applying unified diff patches.

    Returns:
        Callable that applies patch content to files.
    """

    def patch(
        path: Annotated[str, Field(description="File path to patch")],
        patch_content: Annotated[str, Field(description="Unified diff patch content")],
    ) -> str:
        """
        Apply a unified diff patch to a file.

        Args:
            path: Path to the file to patch.
            patch_content: Unified diff content to apply.

        Returns:
            Success or error message.
        """
        try:
            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return f"❌ Error: File not found: {path}"

            if not file_path.is_file():
                return f"❌ Error: Not a file: {path}"

            # Try using the patch command if available
            patch_cmd = _try_system_patch(file_path, patch_content)
            if patch_cmd is not None:
                return patch_cmd

            # Fallback: manual patch application
            return _apply_patch_manually(file_path, patch_content)

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return patch


def _try_system_patch(file_path: Path, patch_content: str) -> str | None:
    """
    Try to apply patch using system patch command.

    Args:
        file_path: Path to file to patch.
        patch_content: Unified diff content.

    Returns:
        Result message if patch command available, None otherwise.
    """
    try:
        result = subprocess.run(
            ["patch", "--dry-run", str(file_path)],
            input=patch_content,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            # Dry run failed, return error
            return f"❌ Error: Patch cannot be applied cleanly: {result.stderr.strip()}"

        # Dry run succeeded, apply for real
        result = subprocess.run(
            ["patch", str(file_path)],
            input=patch_content,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return f"✅ Patch applied successfully to {file_path.name}"

        return f"❌ Error: Patch failed: {result.stderr.strip()}"

    except FileNotFoundError:
        # patch command not available
        return None
    except subprocess.TimeoutExpired:
        return "❌ Error: Patch command timed out"


def _apply_patch_manually(file_path: Path, patch_content: str) -> str:
    """
    Apply a unified diff patch manually by parsing hunks.

    Args:
        file_path: Path to the file to patch.
        patch_content: Unified diff content.

    Returns:
        Success or error message.
    """
    try:
        original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return f"❌ Error: File is not valid UTF-8 text"

    patch_lines = patch_content.splitlines(keepends=True)

    # Parse hunks
    hunks: list[tuple[int, int, list[str]]] = []
    current_hunk_start = -1
    current_hunk_count = 0
    current_hunk_lines: list[str] = []
    in_hunk = False

    for line in patch_lines:
        stripped = line.rstrip("\n\r")

        if stripped.startswith("@@"):
            # Save previous hunk
            if in_hunk and current_hunk_start >= 0:
                hunks.append((current_hunk_start, current_hunk_count, current_hunk_lines))

            # Parse hunk header: @@ -start,count +start,count @@
            try:
                parts = stripped.split("@@")[1].strip()
                old_range = parts.split(" ")[0]  # -start,count
                old_parts = old_range.lstrip("-").split(",")
                current_hunk_start = int(old_parts[0]) - 1  # 0-based
                current_hunk_count = int(old_parts[1]) if len(old_parts) > 1 else 1
            except (IndexError, ValueError):
                return f"❌ Error: Invalid patch hunk header: {stripped}"

            current_hunk_lines = []
            in_hunk = True

        elif in_hunk:
            current_hunk_lines.append(line)

    # Save last hunk
    if in_hunk and current_hunk_start >= 0:
        hunks.append((current_hunk_start, current_hunk_count, current_hunk_lines))

    if not hunks:
        return "❌ Error: No valid hunks found in patch"

    # Apply hunks in reverse order to preserve line numbers
    result_lines = list(original_lines)
    for hunk_start, hunk_count, hunk_lines in reversed(hunks):
        # Remove old lines
        new_lines: list[str] = []
        for hl in hunk_lines:
            if hl.startswith("+"):
                new_lines.append(hl[1:])
            elif hl.startswith("-"):
                continue  # Skip removed lines
            elif hl.startswith(" "):
                new_lines.append(hl[1:])
            # Skip other lines (no-newline markers, etc.)

        result_lines[hunk_start : hunk_start + hunk_count] = new_lines

    file_path.write_text("".join(result_lines), encoding="utf-8")

    return f"✅ Patch applied successfully to {file_path.name} ({len(hunks)} hunk(s))"
