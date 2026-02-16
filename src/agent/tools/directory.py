"""
Directory tools for agent system.

Provides directory listing, tree view, creation, move, and delete operations.
All tools follow FAANG principal engineer quality standards.
"""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field


def create_list_dir_tool() -> Callable[..., str]:
    """
    Create tool for listing directory contents.

    Returns:
        Callable that lists directory contents with file sizes and types.
    """

    def list_dir(
        path: Annotated[str, Field(description="Directory path to list")] = ".",
        show_hidden: Annotated[
            bool, Field(description="Show hidden files (default: False)")
        ] = False,
    ) -> str:
        """
        List directory contents with file sizes and types.

        Args:
            path: Directory path to list.
            show_hidden: Whether to show hidden files/directories.

        Returns:
            Formatted directory listing or error message.
        """
        try:
            dir_path = Path(path).expanduser().resolve()

            if not dir_path.exists():
                return f"❌ Error: Directory not found: {path}"

            if not dir_path.is_dir():
                return f"❌ Error: Not a directory: {path}"

            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

            if not show_hidden:
                entries = [e for e in entries if not e.name.startswith(".")]

            if not entries:
                return f"(empty directory: {path})"

            lines: list[str] = []
            for entry in entries:
                if entry.is_symlink():
                    target = entry.resolve()
                    lines.append(f"[LINK] {entry.name} -> {target}")
                elif entry.is_dir():
                    lines.append(f"[DIR]  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    lines.append(f"[FILE] {size:,} B  {entry.name}")

            return "\n".join(lines)

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except Exception as e:
            return f"❌ Error listing directory: {str(e)}"

    return list_dir


def create_tree_tool() -> Callable[..., str]:
    """
    Create tool for showing directory tree structure.

    Returns:
        Callable that shows a tree view of directory contents.
    """

    def tree(
        path: Annotated[str, Field(description="Root directory for tree")] = ".",
        max_depth: Annotated[
            int, Field(description="Maximum depth to display (max 10)", ge=1, le=10)
        ] = 3,
        show_hidden: Annotated[
            bool, Field(description="Show hidden files (default: False)")
        ] = False,
    ) -> str:
        """
        Show directory tree structure.

        Args:
            path: Root directory for tree view.
            max_depth: Maximum depth to traverse (1-10).
            show_hidden: Whether to show hidden files/directories.

        Returns:
            Tree-formatted directory structure or error message.
        """
        try:
            root_path = Path(path).expanduser().resolve()

            if not root_path.exists():
                return f"❌ Error: Directory not found: {path}"

            if not root_path.is_dir():
                return f"❌ Error: Not a directory: {path}"

            lines: list[str] = [f"{root_path.name}/"]
            entry_count = 0
            max_entries = 200
            truncated = False

            def _walk(dir_path: Path, prefix: str, depth: int) -> None:
                nonlocal entry_count, truncated

                if depth > max_depth or truncated:
                    return

                try:
                    entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                except PermissionError:
                    return

                if not show_hidden:
                    entries = [e for e in entries if not e.name.startswith(".")]

                for i, entry in enumerate(entries):
                    if truncated:
                        return

                    entry_count += 1
                    if entry_count > max_entries:
                        truncated = True
                        return

                    is_last = i == len(entries) - 1
                    connector = "└── " if is_last else "├── "
                    name = f"{entry.name}/" if entry.is_dir() else entry.name
                    lines.append(f"{prefix}{connector}{name}")

                    if entry.is_dir():
                        extension = "    " if is_last else "│   "
                        _walk(entry, prefix + extension, depth + 1)

            _walk(root_path, "", 1)

            result = "\n".join(lines)
            if truncated:
                result += f"\n\n[Truncated at {max_entries} entries]"

            return result

        except Exception as e:
            return f"❌ Error building tree: {str(e)}"

    return tree


def create_mkdir_tool() -> Callable[..., str]:
    """
    Create tool for creating directories.

    Returns:
        Callable that creates directories with parent directories.
    """

    def mkdir(
        path: Annotated[str, Field(description="Directory path to create")],
    ) -> str:
        """
        Create directory with parent directories.

        Args:
            path: Directory path to create.

        Returns:
            Success message or error message.
        """
        try:
            dir_path = Path(path).expanduser().resolve()
            dir_path.mkdir(parents=True, exist_ok=True)
            return f"✅ Created directory: {path}"

        except PermissionError:
            return f"❌ Error: Permission denied: {path}"
        except Exception as e:
            return f"❌ Error creating directory: {str(e)}"

    return mkdir


def create_move_tool() -> Callable[..., str]:
    """
    Create tool for moving/renaming files or directories.

    Returns:
        Callable that moves or renames files and directories.
    """

    def move(
        source: Annotated[str, Field(description="Source file or directory path")],
        destination: Annotated[str, Field(description="Destination path")],
    ) -> str:
        """
        Move or rename a file or directory.

        Args:
            source: Source file or directory path.
            destination: Destination path.

        Returns:
            Success message or error message.
        """
        try:
            src_path = Path(source).expanduser().resolve()

            if not src_path.exists():
                return f"❌ Error: Source not found: {source}"

            shutil.move(str(src_path), str(Path(destination).expanduser().resolve()))
            return f"✅ Moved {source} → {destination}"

        except PermissionError:
            return f"❌ Error: Permission denied"
        except Exception as e:
            return f"❌ Error moving: {str(e)}"

    return move


def create_delete_tool() -> Callable[..., str]:
    """
    Create tool for deleting files or directories.

    Returns:
        Callable that deletes files or directories with safety checks.
    """

    def delete(
        path: Annotated[str, Field(description="File or directory path to delete")],
        recursive: Annotated[
            bool, Field(description="Delete directories recursively (default: False)")
        ] = False,
    ) -> str:
        """
        Delete a file or directory.

        Args:
            path: File or directory path to delete.
            recursive: If True, delete directories recursively.

        Returns:
            Success message or error message.
        """
        try:
            target = Path(path).expanduser().resolve()

            if not target.exists():
                return f"❌ Error: Not found: {path}"

            # Safety: refuse to delete .git directory
            if target.name == ".git" or "/.git/" in str(target) or str(target).endswith("/.git"):
                return f"❌ Error: Refusing to delete .git directory: {path}"

            if target.is_file():
                target.unlink()
                return f"✅ Deleted: {path}"

            if target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                    return f"✅ Deleted: {path}"
                else:
                    target.rmdir()
                    return f"✅ Deleted: {path}"

            return f"❌ Error: Unknown file type: {path}"

        except OSError as e:
            if "not empty" in str(e).lower() or "directory not empty" in str(e).lower():
                return f"❌ Error: Directory not empty: {path}. Use recursive=True to delete."
            return f"❌ Error: {str(e)}"
        except Exception as e:
            return f"❌ Error deleting: {str(e)}"

    return delete
