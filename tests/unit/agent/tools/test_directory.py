"""
Unit tests for directory tools.

Tests cover list_dir, tree, mkdir, move, and delete tools with all edge cases.
Target: 100% code coverage
"""

import pytest

from src.agent.tools.directory import (
    create_delete_tool,
    create_list_dir_tool,
    create_mkdir_tool,
    create_move_tool,
    create_tree_tool,
)


class TestListDirTool:
    """Tests for list_dir tool."""

    def test_list_dir_shows_files_and_dirs(self, tmp_path):
        """Test listing shows both files and directories."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.py").write_text("content")

        tool = create_list_dir_tool()
        result = tool(path=str(tmp_path))

        assert "[DIR]  subdir/" in result
        assert "[FILE]" in result
        assert "file.py" in result

    def test_list_dir_default_path(self, tmp_path, monkeypatch):
        """Test listing with default path (current directory)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "test.txt").write_text("hello")

        tool = create_list_dir_tool()
        result = tool()

        assert "test.txt" in result

    def test_list_dir_show_hidden(self, tmp_path):
        """Test that hidden files are shown when show_hidden=True."""
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("hello")

        tool = create_list_dir_tool()

        # Without show_hidden
        result = tool(path=str(tmp_path), show_hidden=False)
        assert ".hidden" not in result
        assert "visible.txt" in result

        # With show_hidden
        result = tool(path=str(tmp_path), show_hidden=True)
        assert ".hidden" in result
        assert "visible.txt" in result

    def test_list_dir_empty_dir(self, tmp_path):
        """Test listing an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        tool = create_list_dir_tool()
        result = tool(path=str(empty_dir))

        assert "empty directory" in result

    def test_list_dir_not_found(self):
        """Test listing a non-existent directory."""
        tool = create_list_dir_tool()
        result = tool(path="/nonexistent/dir")

        assert "❌ Error: Directory not found" in result

    def test_list_dir_not_a_directory(self, tmp_path):
        """Test listing a file (not a directory)."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        tool = create_list_dir_tool()
        result = tool(path=str(test_file))

        assert "❌ Error: Not a directory" in result


class TestTreeTool:
    """Tests for tree tool."""

    def test_tree_basic_structure(self, tmp_path):
        """Test tree shows correct structure."""
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "file1.py").write_text("")
        (tmp_path / "file2.txt").write_text("")

        tool = create_tree_tool()
        result = tool(path=str(tmp_path))

        assert "dir1/" in result
        assert "file1.py" in result
        assert "file2.txt" in result
        assert "├──" in result or "└──" in result

    def test_tree_max_depth(self, tmp_path):
        """Test tree respects max_depth."""
        # Create depth 3: a/b/c/deep.txt
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("")
        (tmp_path / "a" / "shallow.txt").write_text("")

        tool = create_tree_tool()
        result = tool(path=str(tmp_path), max_depth=2)

        assert "shallow.txt" in result
        # c/ should appear but deep.txt should not (depth 3 > max_depth 2)
        assert "deep.txt" not in result

    def test_tree_show_hidden(self, tmp_path):
        """Test tree respects show_hidden flag."""
        (tmp_path / ".hidden_dir").mkdir()
        (tmp_path / "visible.txt").write_text("")

        tool = create_tree_tool()

        result_no_hidden = tool(path=str(tmp_path), show_hidden=False)
        assert ".hidden_dir" not in result_no_hidden

        result_hidden = tool(path=str(tmp_path), show_hidden=True)
        assert ".hidden_dir" in result_hidden

    def test_tree_empty_dir(self, tmp_path):
        """Test tree on empty directory."""
        empty = tmp_path / "empty"
        empty.mkdir()

        tool = create_tree_tool()
        result = tool(path=str(empty))

        # Should just show root name
        assert "empty/" in result

    def test_tree_truncation_at_200(self, tmp_path):
        """Test tree truncates at 200 entries."""
        for i in range(210):
            (tmp_path / f"file_{i:04d}.txt").write_text("")

        tool = create_tree_tool()
        result = tool(path=str(tmp_path))

        assert "Truncated at 200 entries" in result

    def test_tree_not_found(self):
        """Test tree on non-existent directory."""
        tool = create_tree_tool()
        result = tool(path="/nonexistent/dir")

        assert "❌ Error: Directory not found" in result

    def test_tree_not_a_directory(self, tmp_path):
        """Test tree on a file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        tool = create_tree_tool()
        result = tool(path=str(test_file))

        assert "❌ Error: Not a directory" in result


class TestMkdirTool:
    """Tests for mkdir tool."""

    def test_mkdir_creates_directory(self, tmp_path):
        """Test creating a new directory."""
        new_dir = tmp_path / "new_dir"

        tool = create_mkdir_tool()
        result = tool(path=str(new_dir))

        assert "✅ Created directory" in result
        assert new_dir.is_dir()

    def test_mkdir_creates_parents(self, tmp_path):
        """Test creating nested directories."""
        nested = tmp_path / "a" / "b" / "c"

        tool = create_mkdir_tool()
        result = tool(path=str(nested))

        assert "✅ Created directory" in result
        assert nested.is_dir()

    def test_mkdir_existing_dir_ok(self, tmp_path):
        """Test creating an already existing directory succeeds."""
        existing = tmp_path / "existing"
        existing.mkdir()

        tool = create_mkdir_tool()
        result = tool(path=str(existing))

        assert "✅ Created directory" in result


class TestMoveTool:
    """Tests for move tool."""

    def test_move_file(self, tmp_path):
        """Test moving a file."""
        src = tmp_path / "source.txt"
        src.write_text("content")
        dst = tmp_path / "dest.txt"

        tool = create_move_tool()
        result = tool(source=str(src), destination=str(dst))

        assert "✅ Moved" in result
        assert not src.exists()
        assert dst.read_text() == "content"

    def test_move_directory(self, tmp_path):
        """Test moving a directory."""
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("content")
        dst_dir = tmp_path / "dst_dir"

        tool = create_move_tool()
        result = tool(source=str(src_dir), destination=str(dst_dir))

        assert "✅ Moved" in result
        assert not src_dir.exists()
        assert (dst_dir / "file.txt").read_text() == "content"

    def test_move_source_not_found(self, tmp_path):
        """Test moving a non-existent source."""
        tool = create_move_tool()
        result = tool(source=str(tmp_path / "nonexistent"), destination=str(tmp_path / "dest"))

        assert "❌ Error: Source not found" in result


class TestDeleteTool:
    """Tests for delete tool."""

    def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        tool = create_delete_tool()
        result = tool(path=str(test_file))

        assert "✅ Deleted" in result
        assert not test_file.exists()

    def test_delete_empty_dir(self, tmp_path):
        """Test deleting an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        tool = create_delete_tool()
        result = tool(path=str(empty_dir))

        assert "✅ Deleted" in result
        assert not empty_dir.exists()

    def test_delete_recursive(self, tmp_path):
        """Test deleting a directory recursively."""
        dir_with_files = tmp_path / "dir"
        dir_with_files.mkdir()
        (dir_with_files / "file.txt").write_text("content")
        (dir_with_files / "subdir").mkdir()

        tool = create_delete_tool()
        result = tool(path=str(dir_with_files), recursive=True)

        assert "✅ Deleted" in result
        assert not dir_with_files.exists()

    def test_delete_nonempty_dir_without_recursive(self, tmp_path):
        """Test deleting a non-empty directory without recursive flag."""
        nonempty = tmp_path / "nonempty"
        nonempty.mkdir()
        (nonempty / "file.txt").write_text("content")

        tool = create_delete_tool()
        result = tool(path=str(nonempty))

        assert "❌ Error" in result
        assert nonempty.exists()

    def test_delete_git_directory_refused(self, tmp_path):
        """Test that .git directory deletion is refused."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        tool = create_delete_tool()
        result = tool(path=str(git_dir))

        assert "❌ Error: Refusing to delete .git directory" in result
        assert git_dir.exists()

    def test_delete_not_found(self, tmp_path):
        """Test deleting a non-existent path."""
        tool = create_delete_tool()
        result = tool(path=str(tmp_path / "nonexistent"))

        assert "❌ Error: Not found" in result
