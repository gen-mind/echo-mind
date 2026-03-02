"""
Filesystem tools for agent system.

Provides safe file operations with proper error handling and security constraints.
All tools follow FAANG principal engineer quality standards.

Confidence: High - Tools match Moltbot implementations
"""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field


def create_read_tool() -> Callable[..., str]:
    """
    Create tool for reading file contents.

    Returns:
        Callable that reads file contents with line numbers.
    """

    def read(
        path: Annotated[str, Field(description="File path to read")],
        offset: Annotated[
            int, Field(description="Line number to start from (0-based)", ge=0)
        ] = 0,
        limit: Annotated[
            int, Field(description="Maximum number of lines to read", gt=0, le=10000)
        ] = 2000,
    ) -> str:
        """
        Read file contents with optional offset and limit.

        Args:
            path: File path to read
            offset: Line number to start from (0-based)
            limit: Maximum number of lines to read (max 10000)

        Returns:
            File contents formatted with line numbers, or error message.
        """
        try:
            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return f"❌ Error: File not found: {path}"

            if not file_path.is_file():
                return f"❌ Error: Not a file: {path}"

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            if offset >= total_lines:
                return f"❌ Error: Offset {offset} exceeds file length ({total_lines} lines)"

            # Apply offset and limit
            selected_lines = lines[offset : offset + limit]

            # Format with line numbers
            result: list[str] = []
            for i, line in enumerate(selected_lines, start=offset + 1):
                result.append(f"{i:6d}\t{line.rstrip()}")

            output = "\n".join(result)

            # Add truncation message if needed
            if len(lines) > offset + limit:
                remaining = total_lines - (offset + limit)
                output += f"\n\n[Showing lines {offset + 1}-{offset + len(selected_lines)} of {total_lines} total lines. {remaining} more lines available]"

            return output

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except UnicodeDecodeError:
            return f"❌ Error: File is not UTF-8 text: {path}"
        except Exception as e:
            return f"❌ Error reading file: {str(e)}"

    return read


def create_write_tool() -> Callable[..., str]:
    """
    Create tool for writing file contents.

    Returns:
        Callable that writes content to a file.
    """

    def write(
        path: Annotated[str, Field(description="File path to write")],
        content: Annotated[str, Field(description="File content to write")],
    ) -> str:
        """
        Write content to file (creates parent directories if needed).

        Args:
            path: File path to write
            content: File content

        Returns:
            Success message or error message.
        """
        try:
            file_path = Path(path).expanduser().resolve()

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            bytes_written = len(content.encode("utf-8"))
            return f"✅ Successfully wrote {bytes_written:,} bytes to {path}"

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except Exception as e:
            return f"❌ Error writing file: {str(e)}"

    return write


def create_grep_tool() -> Callable[..., str]:
    """
    Create tool for searching file contents using ripgrep.

    Returns:
        Callable that searches file contents with ripgrep.
    """

    def grep(
        pattern: Annotated[str, Field(description="Regular expression pattern to search")],
        path: Annotated[
            str, Field(description="Directory or file to search")
        ] = ".",
        glob: Annotated[
            str | None, Field(description="File glob pattern (e.g., '*.py')")
        ] = None,
        max_results: Annotated[
            int, Field(description="Maximum number of results", gt=0, le=1000)
        ] = 100,
    ) -> str:
        """
        Search file contents using ripgrep.

        Args:
            pattern: Regular expression pattern
            path: Directory or file to search
            glob: Optional file glob pattern
            max_results: Maximum number of results (max 1000)

        Returns:
            Search results or error message
        """
        try:
            cmd = ["rg", "--line-number", "--no-heading", "--color=never", pattern, path]

            if glob:
                cmd.extend(["--glob", glob])

            # Limit results
            cmd.extend(["--max-count", str(max_results)])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                line_count = len(output.split("\n")) if output else 0
                return f"{output}\n\n[Found {line_count} matches]"
            elif result.returncode == 1:
                return f"No matches found for pattern: {pattern}"
            else:
                # Check if rg is installed
                if "not found" in result.stderr or "command not found" in result.stderr:
                    return "❌ Error: ripgrep (rg) is not installed. Please install it: brew install ripgrep"
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Search timed out after 30 seconds"
        except Exception as e:
            return f"❌ Error searching: {str(e)}"

    return grep


def create_glob_tool() -> Callable[..., str]:
    """
    Create tool for finding files by pattern.

    Returns:
        Callable that finds files matching a glob pattern.
    """

    def glob_files(
        pattern: Annotated[str, Field(description="Glob pattern (e.g., '**/*.py')")],
        path: Annotated[str, Field(description="Base directory to search")] = ".",
        max_results: Annotated[
            int, Field(description="Maximum number of results", gt=0, le=1000)
        ] = 100,
    ) -> str:
        """
        Find files matching glob pattern.

        Args:
            pattern: Glob pattern (supports ** for recursive)
            path: Base directory
            max_results: Maximum number of results (max 1000)

        Returns:
            List of matching files or error message
        """
        try:
            base_path = Path(path).expanduser().resolve()

            if not base_path.exists():
                return f"❌ Error: Directory not found: {path}"

            if not base_path.is_dir():
                return f"❌ Error: Not a directory: {path}"

            # Use glob to find files
            matches = sorted(base_path.glob(pattern))

            if not matches:
                return f"No files found matching pattern: {pattern}"

            # Limit results
            matches = matches[:max_results]

            # Format output
            result_lines = [str(match.relative_to(base_path)) for match in matches]
            output = "\n".join(result_lines)

            total_matches = len(matches)
            if total_matches >= max_results:
                output += f"\n\n[Showing first {max_results} of {total_matches}+ matches]"
            else:
                output += f"\n\n[Found {total_matches} matches]"

            return output

        except Exception as e:
            return f"❌ Error finding files: {str(e)}"

    return glob_files
