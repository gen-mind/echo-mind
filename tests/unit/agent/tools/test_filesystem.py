"""
Unit tests for filesystem tools.

Tests cover read, write, grep, and glob tools with all edge cases.
Target: 100% code coverage
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.filesystem import (
    create_glob_tool,
    create_grep_tool,
    create_read_tool,
    create_write_tool,
)


class TestReadTool:
    """Tests for read tool."""

    def test_read_simple_file(self, tmp_path):
        """Test reading a simple file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        read = create_read_tool()
        result = read(str(test_file))

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert "     1\t" in result  # Line numbers

    def test_read_with_offset(self, tmp_path):
        """Test reading with offset."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join(f"Line {i}" for i in range(1, 11)))

        read = create_read_tool()
        result = read(str(test_file), offset=5, limit=3)

        assert "Line 6" in result
        assert "Line 7" in result
        assert "Line 8" in result
        assert "Line 5" not in result
        assert "Line 9" not in result

    def test_read_with_limit(self, tmp_path):
        """Test reading with limit."""
        test_file = tmp_path / "test.txt"
        lines = "\n".join(f"Line {i}" for i in range(1, 101))
        test_file.write_text(lines)

        read = create_read_tool()
        result = read(str(test_file), limit=10)

        assert "Line 1" in result
        assert "Line 10" in result
        assert "Showing lines 1-10 of 100" in result

    def test_read_nonexistent_file(self):
        """Test reading non-existent file."""
        read = create_read_tool()
        result = read("/nonexistent/file.txt")

        assert "❌" in result
        assert "not found" in result.lower()

    def test_read_directory(self, tmp_path):
        """Test reading a directory (should fail)."""
        read = create_read_tool()
        result = read(str(tmp_path))

        assert "❌" in result
        assert "Not a file" in result


class TestWriteTool:
    """Tests for write tool."""

    def test_write_simple_file(self, tmp_path):
        """Test writing a simple file."""
        test_file = tmp_path / "output.txt"

        write = create_write_tool()
        result = write(str(test_file), "Hello, World!")

        assert "✅" in result
        assert "Successfully wrote" in result
        assert test_file.read_text() == "Hello, World!"

    def test_write_creates_parent_directories(self, tmp_path):
        """Test that write creates parent directories."""
        test_file = tmp_path / "subdir" / "nested" / "file.txt"

        write = create_write_tool()
        result = write(str(test_file), "Content")

        assert "✅" in result
        assert test_file.exists()
        assert test_file.read_text() == "Content"

    def test_write_overwrites_existing_file(self, tmp_path):
        """Test that write overwrites existing file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("Old content")

        write = create_write_tool()
        result = write(str(test_file), "New content")

        assert "✅" in result
        assert test_file.read_text() == "New content"


class TestGrepTool:
    """Tests for grep tool."""

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_finds_matches(self, mock_run):
        """Test grep finds matches."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test.py:1:def hello():\ntest.py:3:    return True",
        )

        grep = create_grep_tool()
        result = grep("def", "/some/path")

        assert "def hello()" in result
        assert "Found" in result
        mock_run.assert_called_once()

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_no_matches(self, mock_run):
        """Test grep with no matches."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
        )

        grep = create_grep_tool()
        result = grep("nonexistent_pattern", "/some/path")

        assert "No matches found" in result

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_with_glob(self, mock_run):
        """Test grep with glob pattern."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test.py:1:def hello():",
        )

        grep = create_grep_tool()
        result = grep("def", "/some/path", glob="*.py")

        assert "hello" in result
        # Verify glob was passed to rg
        call_args = mock_run.call_args[0][0]
        assert "--glob" in call_args
        assert "*.py" in call_args


class TestGlobTool:
    """Tests for glob tool."""

    def test_glob_finds_files(self, tmp_path):
        """Test glob finds files."""
        (tmp_path / "file1.py").write_text("")
        (tmp_path / "file2.py").write_text("")
        (tmp_path / "file3.txt").write_text("")

        glob_tool = create_glob_tool()
        result = glob_tool("*.py", str(tmp_path))

        assert "file1.py" in result
        assert "file2.py" in result
        assert "file3.txt" not in result
        assert "Found 2 matches" in result

    def test_glob_recursive(self, tmp_path):
        """Test recursive glob."""
        (tmp_path / "file1.py").write_text("")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.py").write_text("")

        glob_tool = create_glob_tool()
        result = glob_tool("**/*.py", str(tmp_path))

        assert "file1.py" in result
        assert "file2.py" in result

    def test_glob_no_matches(self, tmp_path):
        """Test glob with no matches."""
        glob_tool = create_glob_tool()
        result = glob_tool("*.nonexistent", str(tmp_path))

        assert "No files found" in result

    def test_glob_nonexistent_directory(self):
        """Test glob on non-existent directory."""
        glob_tool = create_glob_tool()
        result = glob_tool("*", "/nonexistent")

        assert "❌" in result
        assert "not found" in result.lower()

    def test_glob_path_is_file_not_directory(self, tmp_path):
        """Test glob on a path that is a file, not a directory."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        glob_tool = create_glob_tool()
        result = glob_tool("*", str(test_file))

        assert "❌" in result
        assert "Not a directory" in result

    def test_glob_results_truncated(self, tmp_path):
        """Test glob truncates results at max_results."""
        # Create 5 files
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text("")

        glob_tool = create_glob_tool()
        result = glob_tool("*.txt", str(tmp_path), max_results=3)

        assert "Showing first 3" in result

    def test_glob_generic_exception(self, tmp_path):
        """Test glob handles generic exceptions."""
        glob_tool = create_glob_tool()

        with patch("src.agent.tools.filesystem.Path.expanduser", side_effect=RuntimeError("boom")):
            result = glob_tool("*.py", str(tmp_path))

        assert "❌" in result
        assert "boom" in result


class TestReadToolEdgeCases:
    """Tests for read tool error paths."""

    def test_read_offset_exceeds_length(self, tmp_path):
        """Test reading with offset beyond file length."""
        test_file = tmp_path / "short.txt"
        test_file.write_text("Line 1\nLine 2\n")

        read = create_read_tool()
        result = read(str(test_file), offset=100)

        assert "❌" in result
        assert "Offset 100 exceeds file length" in result

    def test_read_permission_error(self, tmp_path):
        """Test reading a file with permission error."""
        read = create_read_tool()

        with patch("builtins.open", side_effect=PermissionError("denied")):
            # Need a file that exists and is a file
            test_file = tmp_path / "secret.txt"
            test_file.write_text("secret")
            result = read(str(test_file))

        assert "❌" in result
        assert "Permission denied" in result

    def test_read_unicode_decode_error(self, tmp_path):
        """Test reading a binary file triggers unicode error."""
        read = create_read_tool()

        with patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")):
            test_file = tmp_path / "binary.dat"
            test_file.write_bytes(b"\xff\xfe")
            result = read(str(test_file))

        assert "❌" in result
        assert "not UTF-8" in result

    def test_read_generic_exception(self, tmp_path):
        """Test reading handles generic exceptions."""
        read = create_read_tool()

        with patch("builtins.open", side_effect=RuntimeError("disk error")):
            test_file = tmp_path / "file.txt"
            test_file.write_text("data")
            result = read(str(test_file))

        assert "❌" in result
        assert "disk error" in result


class TestWriteToolEdgeCases:
    """Tests for write tool error paths."""

    def test_write_permission_error(self, tmp_path):
        """Test writing with permission error."""
        write = create_write_tool()

        with patch("builtins.open", side_effect=PermissionError("read-only")):
            result = write(str(tmp_path / "file.txt"), "content")

        assert "❌" in result
        assert "Permission denied" in result

    def test_write_generic_exception(self, tmp_path):
        """Test writing handles generic exceptions."""
        write = create_write_tool()

        with patch("builtins.open", side_effect=RuntimeError("disk full")):
            result = write(str(tmp_path / "file.txt"), "content")

        assert "❌" in result
        assert "disk full" in result


class TestGrepToolEdgeCases:
    """Tests for grep tool error paths."""

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_rg_not_installed(self, mock_run):
        """Test grep when ripgrep is not installed."""
        mock_run.return_value = MagicMock(
            returncode=127,
            stdout="",
            stderr="command not found: rg",
        )

        grep = create_grep_tool()
        result = grep("pattern", "/some/path")

        assert "❌" in result
        assert "ripgrep" in result.lower() or "not installed" in result.lower()

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_other_error(self, mock_run):
        """Test grep with unexpected error code and stderr."""
        mock_run.return_value = MagicMock(
            returncode=2,
            stdout="",
            stderr="Invalid regex syntax",
        )

        grep = create_grep_tool()
        result = grep("[invalid", "/some/path")

        assert "❌" in result
        assert "Invalid regex syntax" in result

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_timeout(self, mock_run):
        """Test grep timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rg", timeout=30)

        grep = create_grep_tool()
        result = grep("pattern", "/some/path")

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.filesystem.subprocess.run")
    def test_grep_generic_exception(self, mock_run):
        """Test grep handles generic exceptions."""
        mock_run.side_effect = RuntimeError("broken pipe")

        grep = create_grep_tool()
        result = grep("pattern", "/some/path")

        assert "❌" in result
        assert "broken pipe" in result
