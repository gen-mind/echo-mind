"""
Unit tests for text tools.

Tests cover diff and patch tools with all edge cases.
Target: 100% code coverage
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.text import create_diff_tool, create_patch_tool


class TestDiffTool:
    """Tests for diff tool."""

    def test_diff_identical_files(self, tmp_path):
        """Test diff of identical files."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("same content\n")
        file_b.write_text("same content\n")

        tool = create_diff_tool()
        result = tool(str(file_a), str(file_b))

        assert result == "(files are identical)"

    def test_diff_different_files(self, tmp_path):
        """Test diff of different files."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("line 1\nline 2\nline 3\n")
        file_b.write_text("line 1\nmodified\nline 3\n")

        tool = create_diff_tool()
        result = tool(str(file_a), str(file_b))

        assert "---" in result
        assert "+++" in result
        assert "-line 2" in result
        assert "+modified" in result

    def test_diff_file_not_found(self, tmp_path):
        """Test diff with non-existent file."""
        file_a = tmp_path / "a.txt"
        file_a.write_text("content\n")

        tool = create_diff_tool()
        result = tool(str(file_a), "/nonexistent/file.txt")

        assert "❌ Error" in result
        assert "not found" in result.lower()

    def test_diff_context_lines(self, tmp_path):
        """Test diff with custom context lines."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        lines_a = [f"line {i}\n" for i in range(20)]
        lines_b = list(lines_a)
        lines_b[10] = "changed line 10\n"
        file_a.write_text("".join(lines_a))
        file_b.write_text("".join(lines_b))

        tool = create_diff_tool()

        # With 0 context lines
        result_0 = tool(str(file_a), str(file_b), context_lines=0)
        assert "-line 10" in result_0
        assert "+changed line 10" in result_0

        # With 1 context line
        result_1 = tool(str(file_a), str(file_b), context_lines=1)
        assert "line 9" in result_1
        assert "line 11" in result_1

    def test_diff_returns_unified_format(self, tmp_path):
        """Test that diff returns proper unified format."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("old\n")
        file_b.write_text("new\n")

        tool = create_diff_tool()
        result = tool(str(file_a), str(file_b))

        assert result.startswith("---")
        assert "@@" in result

    def test_diff_permission_error(self, tmp_path):
        """Test diff with permission error."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("content\n")
        file_b.write_text("content\n")

        tool = create_diff_tool()

        with patch.object(type(file_a), "read_text", side_effect=PermissionError("denied")):
            result = tool(str(file_a), str(file_b))

        assert "❌ Error" in result
        assert "Permission denied" in result


class TestPatchTool:
    """Tests for patch tool."""

    @patch("src.agent.tools.text.subprocess.run")
    def test_patch_apply_success(self, mock_run, tmp_path):
        """Test successful patch application via system patch."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        # Mock dry run success then actual success
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        tool = create_patch_tool()
        patch_content = "--- a/test.txt\n+++ b/test.txt\n@@ -1,3 +1,3 @@\n line 1\n-line 2\n+modified\n line 3\n"
        result = tool(str(test_file), patch_content)

        assert "✅" in result
        assert "applied successfully" in result

    def test_patch_file_not_found(self):
        """Test patching a non-existent file."""
        tool = create_patch_tool()
        result = tool("/nonexistent/file.txt", "some patch")

        assert "❌ Error" in result
        assert "not found" in result.lower()

    @patch("src.agent.tools.text.subprocess.run")
    def test_patch_invalid_format(self, mock_run, tmp_path):
        """Test patching with invalid patch content via manual fallback."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n")

        # System patch not available
        mock_run.side_effect = FileNotFoundError()

        tool = create_patch_tool()
        result = tool(str(test_file), "this is not a valid patch")

        assert "❌ Error" in result
        assert "No valid hunks" in result

    @patch("src.agent.tools.text.subprocess.run")
    def test_patch_creates_expected_output(self, mock_run, tmp_path):
        """Test manual patch application creates correct output."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        # System patch not available, use manual fallback
        mock_run.side_effect = FileNotFoundError()

        tool = create_patch_tool()
        patch_content = (
            "--- a/test.txt\n"
            "+++ b/test.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line 1\n"
            "-line 2\n"
            "+modified\n"
            " line 3\n"
        )
        result = tool(str(test_file), patch_content)

        assert "✅" in result
        assert test_file.read_text() == "line 1\nmodified\nline 3\n"

    def test_patch_permission_error(self, tmp_path):
        """Test patch with permission error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n")

        tool = create_patch_tool()

        with patch("src.agent.tools.text.Path.expanduser") as mock_expand:
            mock_path = MagicMock()
            mock_path.resolve.return_value = mock_path
            mock_path.exists.return_value = True
            mock_path.is_file.return_value = True
            mock_expand.return_value = mock_path

            # Make the patch function raise PermissionError
            with patch("src.agent.tools.text._try_system_patch", side_effect=PermissionError("denied")):
                result = tool(str(test_file), "patch content")

        assert "❌ Error" in result
        assert "Permission denied" in result

    @patch("src.agent.tools.text.subprocess.run")
    def test_patch_dry_run_fails(self, mock_run, tmp_path):
        """Test when patch dry run fails."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Hunk FAILED",
        )

        tool = create_patch_tool()
        result = tool(str(test_file), "bad patch")

        assert "❌ Error" in result
        assert "cannot be applied" in result
