"""
Unit tests for edit tools.

Tests cover search-and-replace editing with all edge cases.
Target: 100% code coverage
"""

from unittest.mock import patch

import pytest

from src.agent.tools.edit import create_edit_tool


class TestEditTool:
    """Tests for edit tool."""

    def test_edit_replaces_text(self, tmp_path):
        """Test basic text replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="Hello", new_string="Goodbye")

        assert "✅" in result
        assert test_file.read_text() == "Goodbye World"

    def test_edit_returns_diff_preview(self, tmp_path):
        """Test that edit returns a unified diff preview."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nold_value\nline3\n")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="old_value", new_string="new_value")

        assert "✅ Applied edit to" in result
        assert "-old_value" in result
        assert "+new_value" in result

    def test_edit_file_not_found(self):
        """Test error when file does not exist."""
        edit = create_edit_tool()
        result = edit(path="/nonexistent/file.txt", old_string="a", new_string="b")

        assert "❌ Error: File not found" in result

    def test_edit_not_a_file(self, tmp_path):
        """Test error when path is a directory."""
        edit = create_edit_tool()
        result = edit(path=str(tmp_path), old_string="a", new_string="b")

        assert "❌ Error: Not a file" in result

    def test_edit_old_string_not_found(self, tmp_path):
        """Test error when old_string is not in file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="nonexistent", new_string="replacement")

        assert "❌ Error: old_string not found" in result

    def test_edit_identical_strings(self, tmp_path):
        """Test error when old_string equals new_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="Hello", new_string="Hello")

        assert "❌ Error: old_string and new_string are identical" in result

    def test_edit_replace_all_true(self, tmp_path):
        """Test replacing all occurrences when replace_all=True."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo bar foo baz foo")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="foo", new_string="qux", replace_all=True)

        assert "✅" in result
        assert test_file.read_text() == "qux bar qux baz qux"

    def test_edit_replace_all_false_multiple_occurrences(self, tmp_path):
        """Test that only first occurrence is replaced when replace_all=False."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo bar foo baz foo")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="foo", new_string="qux", replace_all=False)

        assert "✅" in result
        assert test_file.read_text() == "qux bar foo baz foo"

    def test_edit_preserves_other_content(self, tmp_path):
        """Test that content outside the replacement is preserved."""
        test_file = tmp_path / "test.txt"
        original = "line1\nline2\ntarget_line\nline4\nline5\n"
        test_file.write_text(original)

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="target_line", new_string="replaced_line")

        content = test_file.read_text()
        assert "✅" in result
        assert "line1\nline2\nreplaced_line\nline4\nline5\n" == content

    def test_edit_empty_old_string(self, tmp_path):
        """Test error when old_string is empty."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        edit = create_edit_tool()
        result = edit(path=str(test_file), old_string="", new_string="something")

        assert "❌ Error: old_string cannot be empty" in result

    def test_edit_permission_error(self, tmp_path):
        """Test error when file cannot be read due to permissions."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        edit = create_edit_tool()

        with patch.object(
            type(test_file), "read_text", side_effect=PermissionError("denied")
        ):
            result = edit(path=str(test_file), old_string="Hello", new_string="Bye")

        assert "❌ Error: Permission denied" in result

    def test_edit_multiline_strings(self, tmp_path):
        """Test editing multiline text blocks."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

        edit = create_edit_tool()
        result = edit(
            path=str(test_file),
            old_string="def foo():\n    pass",
            new_string="def foo():\n    return 42",
        )

        assert "✅" in result
        content = test_file.read_text()
        assert "return 42" in content
        assert "def bar():\n    pass\n" in content
