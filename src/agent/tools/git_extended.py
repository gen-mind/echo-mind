"""
Extended git tools for agent system.

Provides additional git operations beyond the core git tools.
All tools follow FAANG principal engineer quality standards.
"""

import shlex
import subprocess
from collections.abc import Callable
from typing import Annotated

from pydantic import Field

_VALID_BRANCH_ACTIONS = {"list", "create", "delete"}
_VALID_STASH_ACTIONS = {"push", "pop", "list", "drop"}
_VALID_TAG_ACTIONS = {"list", "create", "delete"}


def create_git_branch_tool() -> Callable[..., str]:
    """
    Create tool for managing git branches.

    Returns:
        Callable that lists, creates, or deletes branches.
    """

    def git_branch(
        action: Annotated[
            str, Field(description="Branch action: 'list', 'create', or 'delete'")
        ] = "list",
        name: Annotated[
            str | None, Field(description="Branch name (required for create/delete)")
        ] = None,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        List, create, or delete git branches.

        Args:
            action: Branch action ('list', 'create', 'delete')
            name: Branch name (required for create/delete)
            cwd: Working directory (defaults to current directory)

        Returns:
            Branch operation result or error message.
        """
        if action not in _VALID_BRANCH_ACTIONS:
            return f"❌ Error: Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_BRANCH_ACTIONS))}"

        if action in ("create", "delete") and not name:
            return f"❌ Error: Branch name is required for '{action}' action"

        try:
            if action == "list":
                cmd = ["git", "branch", "-a"]
            elif action == "create":
                cmd = ["git", "branch", name]
            else:  # delete
                cmd = ["git", "branch", "-d", name]

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_branch


def create_git_checkout_tool() -> Callable[..., str]:
    """
    Create tool for switching branches or restoring files.

    Returns:
        Callable that switches branches or restores files.
    """

    def git_checkout(
        target: Annotated[
            str, Field(description="Branch name or file path to checkout")
        ],
        create_branch: Annotated[
            bool, Field(description="Create a new branch (-b flag)")
        ] = False,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Switch branches or restore working tree files.

        Args:
            target: Branch name or file path
            create_branch: If True, create and switch to new branch
            cwd: Working directory (defaults to current directory)

        Returns:
            Checkout result or error message.
        """
        try:
            if create_branch:
                cmd = ["git", "checkout", "-b", target]
            else:
                cmd = ["git", "checkout", target]

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                output = result.stdout or result.stderr
                return output if output.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_checkout


def create_git_stash_tool() -> Callable[..., str]:
    """
    Create tool for git stash operations.

    Returns:
        Callable that manages git stash.
    """

    def git_stash(
        action: Annotated[
            str, Field(description="Stash action: 'push', 'pop', 'list', or 'drop'")
        ] = "push",
        message: Annotated[
            str | None, Field(description="Stash message (only for push)")
        ] = None,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Manage git stash (save, restore, list, drop changes).

        Args:
            action: Stash action ('push', 'pop', 'list', 'drop')
            message: Optional message for push action
            cwd: Working directory (defaults to current directory)

        Returns:
            Stash operation result or error message.
        """
        if action not in _VALID_STASH_ACTIONS:
            return f"❌ Error: Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_STASH_ACTIONS))}"

        try:
            if action == "push":
                cmd = ["git", "stash", "push", "-m", message] if message else ["git", "stash", "push"]
            elif action == "pop":
                cmd = ["git", "stash", "pop"]
            elif action == "list":
                cmd = ["git", "stash", "list"]
            else:  # drop
                cmd = ["git", "stash", "drop"]

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_stash


def create_git_push_tool() -> Callable[..., str]:
    """
    Create tool for pushing to remote.

    Returns:
        Callable that pushes commits to a remote repository.
    """

    def git_push(
        remote: Annotated[
            str, Field(description="Remote name")
        ] = "origin",
        branch: Annotated[
            str | None, Field(description="Branch name (optional)")
        ] = None,
        set_upstream: Annotated[
            bool, Field(description="Set upstream tracking reference")
        ] = False,
        force_with_lease: Annotated[
            bool, Field(description="Use --force-with-lease (safer than --force)")
        ] = False,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Push commits to a remote repository.

        Never allows --force. Only --force-with-lease is available for safety.

        Args:
            remote: Remote name (default: origin)
            branch: Branch name (optional, pushes current branch if omitted)
            set_upstream: Set upstream tracking reference
            force_with_lease: Use --force-with-lease (safer alternative to --force)
            cwd: Working directory (defaults to current directory)

        Returns:
            Push result or error message.
        """
        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            if set_upstream:
                cmd.append("--set-upstream")
            if force_with_lease:
                cmd.append("--force-with-lease")

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                output = result.stdout or result.stderr
                return output if output.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_push


def create_git_pull_tool() -> Callable[..., str]:
    """
    Create tool for pulling from remote.

    Returns:
        Callable that pulls commits from a remote repository.
    """

    def git_pull(
        remote: Annotated[
            str, Field(description="Remote name")
        ] = "origin",
        branch: Annotated[
            str | None, Field(description="Branch name (optional)")
        ] = None,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Pull commits from a remote repository.

        Args:
            remote: Remote name (default: origin)
            branch: Branch name (optional, pulls current branch if omitted)
            cwd: Working directory (defaults to current directory)

        Returns:
            Pull result or error message.
        """
        try:
            cmd = ["git", "pull", remote]
            if branch:
                cmd.append(branch)

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_pull


def create_git_reset_tool() -> Callable[..., str]:
    """
    Create tool for unstaging files.

    Returns:
        Callable that unstages files (mixed reset only, for safety).
    """

    def git_reset(
        files: Annotated[
            str, Field(description="Files to unstage (e.g., '.' or 'src/file.py')")
        ] = ".",
        mode: Annotated[
            str, Field(description="Reset mode (only 'mixed' is allowed for safety)")
        ] = "mixed",
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Unstage files (mixed reset only).

        Only --mixed reset is allowed for safety. Hard reset is blocked
        to prevent accidental data loss.

        Args:
            files: Files to unstage
            mode: Reset mode (only 'mixed' allowed)
            cwd: Working directory (defaults to current directory)

        Returns:
            Reset result or error message.
        """
        if mode != "mixed":
            return "❌ Error: Only --mixed reset is allowed for safety. Use git checkout to discard changes."

        try:
            cmd = ["git", "reset", "--mixed"] + shlex.split(files)

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_reset


def create_git_clone_tool() -> Callable[..., str]:
    """
    Create tool for cloning repositories.

    Returns:
        Callable that clones a git repository.
    """

    def git_clone(
        url: Annotated[str, Field(description="Repository URL to clone")],
        directory: Annotated[
            str | None, Field(description="Target directory (optional)")
        ] = None,
        depth: Annotated[
            int | None, Field(description="Shallow clone depth (optional)", gt=0)
        ] = None,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Clone a git repository.

        Args:
            url: Repository URL
            directory: Target directory (optional)
            depth: Shallow clone depth (optional)
            cwd: Working directory (defaults to current directory)

        Returns:
            Clone result or error message.
        """
        try:
            cmd = ["git", "clone", url]
            if directory:
                cmd.append(directory)
            if depth:
                cmd.extend(["--depth", str(depth)])

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                output = result.stdout or result.stderr
                return output if output.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_clone


def create_git_tag_tool() -> Callable[..., str]:
    """
    Create tool for managing git tags.

    Returns:
        Callable that lists, creates, or deletes tags.
    """

    def git_tag(
        action: Annotated[
            str, Field(description="Tag action: 'list', 'create', or 'delete'")
        ] = "list",
        name: Annotated[
            str | None, Field(description="Tag name (required for create/delete)")
        ] = None,
        message: Annotated[
            str | None, Field(description="Tag message (creates annotated tag)")
        ] = None,
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        List, create, or delete git tags.

        Args:
            action: Tag action ('list', 'create', 'delete')
            name: Tag name (required for create/delete)
            message: Tag message (creates annotated tag if provided)
            cwd: Working directory (defaults to current directory)

        Returns:
            Tag operation result or error message.
        """
        if action not in _VALID_TAG_ACTIONS:
            return f"❌ Error: Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_TAG_ACTIONS))}"

        if action in ("create", "delete") and not name:
            return f"❌ Error: Tag name is required for '{action}' action"

        try:
            if action == "list":
                cmd = ["git", "tag", "-l"]
            elif action == "create":
                if message:
                    cmd = ["git", "tag", "-a", name, "-m", message]
                else:
                    cmd = ["git", "tag", name]
            else:  # delete
                cmd = ["git", "tag", "-d", name]

            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no output)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_tag
