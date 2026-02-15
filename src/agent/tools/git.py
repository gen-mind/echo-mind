"""
Git tools for agent system.

Provides safe git operations with proper error handling.
All tools follow FAANG principal engineer quality standards.

Confidence: High - Tools match Moltbot implementations
"""

import subprocess
from collections.abc import Callable
from typing import Annotated

from pydantic import Field


def create_git_log_tool() -> Callable[..., str]:
    """
    Create tool for showing git commit history.

    Returns:
        Callable that shows git commit history.
    """

    def git_log(
        args: Annotated[
            str, Field(description="Git log arguments (e.g., '--oneline -10', '--author=alice')")
        ] = "--oneline -10",
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Show git commit history.

        Args:
            args: Git log arguments
            cwd: Working directory (defaults to current directory)

        Returns:
            Git log output or error message
        """
        try:
            cmd = f"git log {args}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else "(no commits)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_log


def create_git_diff_tool() -> Callable[..., str]:
    """
    Create tool for showing git changes.

    Returns:
        Callable that shows git diff output.
    """

    def git_diff(
        args: Annotated[
            str, Field(description="Git diff arguments (e.g., 'HEAD', '--staged', 'main..develop')")
        ] = "",
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Show git changes (diff).

        Args:
            args: Git diff arguments
            cwd: Working directory (defaults to current directory)

        Returns:
            Git diff output or error message
        """
        try:
            cmd = f"git diff {args}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                output = result.stdout

                # Truncate if too long (> 20000 characters)
                max_length = 20000
                if len(output) > max_length:
                    output = (
                        output[:max_length]
                        + f"\n\n[Diff truncated at {max_length:,} characters. Use specific file paths to see more.]"
                    )

                return output if output.strip() else "(no changes)"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_diff


def create_git_status_tool() -> Callable[..., str]:
    """
    Create tool for showing git status.

    Returns:
        Callable that shows git working tree status.
    """

    def git_status(
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Show git working tree status.

        Args:
            cwd: Working directory (defaults to current directory)

        Returns:
            Git status output or error message
        """
        try:
            cmd = "git status"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_status


def create_git_add_tool() -> Callable[..., str]:
    """
    Create tool for staging files.

    Returns:
        Callable that stages files for git commit.
    """

    def git_add(
        files: Annotated[str, Field(description="Files to stage (e.g., '.' or 'src/file.py')")],
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Stage files for commit.

        Args:
            files: Files to stage (space-separated or patterns)
            cwd: Working directory (defaults to current directory)

        Returns:
            Success message or error
        """
        try:
            cmd = f"git add {files}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                # Run git status to show what was staged
                status_cmd = "git status --short"
                status_result = subprocess.run(
                    status_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=cwd,
                )
                return f"✅ Staged files: {files}\n\n{status_result.stdout}"
            else:
                return f"❌ Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_add


def create_git_commit_tool() -> Callable[..., str]:
    """
    Create tool for creating commits.

    Returns:
        Callable that creates git commits.
    """

    def git_commit(
        message: Annotated[str, Field(description="Commit message")],
        cwd: Annotated[
            str | None, Field(description="Working directory (optional)")
        ] = None,
    ) -> str:
        """
        Create a git commit.

        Args:
            message: Commit message
            cwd: Working directory (defaults to current directory)

        Returns:
            Commit result or error message
        """
        try:
            if not message.strip():
                return "❌ Error: Commit message cannot be empty"

            # Use heredoc for proper message formatting
            cmd = f"""git commit -m "$(cat <<'EOF'
{message}

Co-Authored-By: EchoMind Agent <agent@echomind.ai>
EOF
)"
"""
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )

            if result.returncode == 0:
                return f"✅ Commit created successfully:\n\n{result.stdout}"
            else:
                # Common errors
                stderr = result.stderr
                if "nothing to commit" in stderr:
                    return "❌ Error: No changes to commit. Stage files first using git_add."
                elif "please tell me who you are" in stderr:
                    return "❌ Error: Git user.name and user.email not configured."
                else:
                    return f"❌ Error: {stderr}"

        except subprocess.TimeoutExpired:
            return "❌ Error: Git command timed out"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return git_commit
