"""
Unit tests for system tools.

Tests cover env_get, which, and find_replace tools with all edge cases.
Target: 100% code coverage
"""

import os
from unittest.mock import patch

import pytest

from src.agent.tools.system import (
    create_env_get_tool,
    create_find_replace_tool,
    create_which_tool,
)


class TestEnvGetTool:
    """Tests for env_get tool."""

    @patch.dict(os.environ, {"MY_VAR": "hello"})
    def test_env_get_existing_var(self):
        """Test getting an existing environment variable."""
        tool = create_env_get_tool()
        result = tool("MY_VAR")

        assert result == "hello"

    def test_env_get_missing_var(self):
        """Test getting a non-existent environment variable."""
        tool = create_env_get_tool()
        result = tool("DEFINITELY_NOT_SET_XYZ_123")

        assert "❌ Error" in result
        assert "not set" in result

    @pytest.mark.parametrize("var_name", [
        "DB_PASSWORD",
        "API_SECRET",
        "AUTH_TOKEN",
        "MY_API_KEY",
        "SSH_PRIVATE_KEY",
    ])
    def test_env_get_sensitive_var_blocked(self, var_name):
        """Test that sensitive variable names are blocked."""
        tool = create_env_get_tool()
        result = tool(var_name)

        assert "❌ Error" in result
        assert "blocked" in result

    def test_env_get_case_insensitive_block(self):
        """Test that sensitive variable blocking is case-insensitive."""
        tool = create_env_get_tool()

        for name in ["my_Password_here", "Secret_Stuff", "some_token_value"]:
            result = tool(name)
            assert "❌ Error" in result
            assert "blocked" in result


class TestWhichTool:
    """Tests for which tool."""

    @patch("src.agent.tools.system.shutil.which")
    def test_which_found(self, mock_which):
        """Test finding an existing command."""
        mock_which.return_value = "/usr/bin/python3"

        tool = create_which_tool()
        result = tool("python3")

        assert result == "/usr/bin/python3"

    @patch("src.agent.tools.system.shutil.which")
    def test_which_not_found(self, mock_which):
        """Test command not found."""
        mock_which.return_value = None

        tool = create_which_tool()
        result = tool("nonexistent_cmd")

        assert "❌ Error" in result
        assert "not found in PATH" in result


class TestFindReplaceTool:
    """Tests for find_replace tool."""

    def test_find_replace_dry_run(self, tmp_path):
        """Test dry run shows what would change."""
        test_file = tmp_path / "test.py"
        test_file.write_text("foo = 1\nbar = foo + 2\n")

        tool = create_find_replace_tool()
        result = tool("foo", "baz", path=str(tmp_path), glob_pattern="*.py", dry_run=True)

        assert "DRY RUN" in result
        assert "Would modify" in result
        assert "test.py" in result
        # File should not be changed
        assert test_file.read_text() == "foo = 1\nbar = foo + 2\n"

    def test_find_replace_actual(self, tmp_path):
        """Test actual replacement modifies files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("foo = 1\nbar = foo + 2\n")

        tool = create_find_replace_tool()
        result = tool("foo", "baz", path=str(tmp_path), glob_pattern="*.py", dry_run=False)

        assert "Modified" in result
        assert "test.py" in result
        assert test_file.read_text() == "baz = 1\nbar = baz + 2\n"

    def test_find_replace_no_matches(self, tmp_path):
        """Test when no files contain the pattern."""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello world\n")

        tool = create_find_replace_tool()
        result = tool("nonexistent_pattern", "replacement", path=str(tmp_path), glob_pattern="*.py")

        assert "No matches found" in result

    def test_find_replace_regex_pattern(self, tmp_path):
        """Test regex pattern replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("date: 2025-01-15\ndate: 2025-02-20\n")

        tool = create_find_replace_tool()
        result = tool(r"(\d{4})-(\d{2})-(\d{2})", r"\2/\3/\1", path=str(tmp_path), glob_pattern="*.txt", dry_run=False)

        assert "Modified" in result
        assert test_file.read_text() == "date: 01/15/2025\ndate: 02/20/2025\n"

    def test_find_replace_binary_skip(self, tmp_path):
        """Test that binary files are skipped."""
        binary_file = tmp_path / "binary.dat"
        binary_file.write_bytes(b"\xff\xfe\x00\x01pattern\x00\x02")

        text_file = tmp_path / "text.txt"
        text_file.write_text("pattern here\n")

        tool = create_find_replace_tool()
        result = tool("pattern", "replaced", path=str(tmp_path), glob_pattern="*", dry_run=False)

        assert "Modified 1 file" in result
        assert text_file.read_text() == "replaced here\n"

    def test_find_replace_max_files_limit(self, tmp_path):
        """Test that too many files returns error."""
        for i in range(101):
            (tmp_path / f"file{i}.txt").write_text("content")

        tool = create_find_replace_tool()
        result = tool("content", "new", path=str(tmp_path), glob_pattern="*.txt")

        assert "❌ Error" in result
        assert "Too many files" in result

    def test_find_replace_invalid_regex(self, tmp_path):
        """Test invalid regex pattern."""
        tool = create_find_replace_tool()
        result = tool("[invalid", "replacement", path=str(tmp_path))

        assert "❌ Error" in result
        assert "Invalid regex" in result

    def test_find_replace_nonexistent_directory(self):
        """Test with non-existent directory."""
        tool = create_find_replace_tool()
        result = tool("pattern", "replacement", path="/nonexistent/dir")

        assert "❌ Error" in result
        assert "not found" in result.lower()
