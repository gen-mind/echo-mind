"""Tools registry, implementations, and middleware."""

from .directory import (
    create_delete_tool,
    create_list_dir_tool,
    create_mkdir_tool,
    create_move_tool,
    create_tree_tool,
)
from .edit import create_edit_tool
from .execution import create_bash_tool
from .filesystem import create_glob_tool, create_grep_tool, create_read_tool, create_write_tool
from .git import (
    create_git_add_tool,
    create_git_commit_tool,
    create_git_diff_tool,
    create_git_log_tool,
    create_git_status_tool,
)
from .git_extended import (
    create_git_branch_tool,
    create_git_checkout_tool,
    create_git_clone_tool,
    create_git_pull_tool,
    create_git_push_tool,
    create_git_reset_tool,
    create_git_stash_tool,
    create_git_tag_tool,
)
from .middleware import PathRestrictionMiddleware
from .registry import ToolsRegistry
from .system import create_env_get_tool, create_find_replace_tool, create_which_tool
from .text import create_diff_tool, create_patch_tool
from .web import create_http_request_tool

__all__ = [
    # Registry
    "ToolsRegistry",
    # Middleware
    "PathRestrictionMiddleware",
    # Filesystem tools
    "create_read_tool",
    "create_write_tool",
    "create_grep_tool",
    "create_glob_tool",
    # Edit tool
    "create_edit_tool",
    # Directory tools
    "create_list_dir_tool",
    "create_tree_tool",
    "create_mkdir_tool",
    "create_move_tool",
    "create_delete_tool",
    # Execution tools
    "create_bash_tool",
    # Web tools
    "create_http_request_tool",
    # Core git tools
    "create_git_log_tool",
    "create_git_diff_tool",
    "create_git_status_tool",
    "create_git_add_tool",
    "create_git_commit_tool",
    # Extended git tools
    "create_git_branch_tool",
    "create_git_checkout_tool",
    "create_git_stash_tool",
    "create_git_push_tool",
    "create_git_pull_tool",
    "create_git_reset_tool",
    "create_git_clone_tool",
    "create_git_tag_tool",
    # System tools
    "create_env_get_tool",
    "create_which_tool",
    "create_find_replace_tool",
    # Text tools
    "create_diff_tool",
    "create_patch_tool",
]
