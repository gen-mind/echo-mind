"""
Unit tests for git tools.

Tests cover git_log, git_diff, git_status, git_add, and git_commit tools.
All subprocess.run calls are mocked — no real git commands are executed.
Target: 100% code coverage
"""

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from src.agent.tools.git import (
    create_git_add_tool,
    create_git_commit_tool,
    create_git_diff_tool,
    create_git_log_tool,
    create_git_status_tool,
)


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------

class TestGitLogTool:
    """Tests for git_log tool."""

    def test_returns_callable(self):
        """Test factory returns callable."""
        assert callable(create_git_log_tool())

    @patch("src.agent.tools.git.subprocess.run")
    def test_default_args(self, mock_run):
        """Test default arguments (--oneline -10)."""
        mock_run.return_value = MagicMock(
            stdout="abc123 Initial commit\n", stderr="", returncode=0,
        )
        git_log = create_git_log_tool()
        result = git_log()

        mock_run.assert_called_once_with(
            "git log --oneline -10",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "abc123" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_custom_args(self, mock_run):
        """Test custom args are passed through."""
        mock_run.return_value = MagicMock(
            stdout="log output", stderr="", returncode=0,
        )
        git_log = create_git_log_tool()
        git_log(args="--author=alice -5")

        assert "git log --author=alice -5" in mock_run.call_args[0][0]

    @patch("src.agent.tools.git.subprocess.run")
    def test_with_cwd(self, mock_run):
        """Test working directory is passed."""
        mock_run.return_value = MagicMock(
            stdout="ok", stderr="", returncode=0,
        )
        git_log = create_git_log_tool()
        git_log(cwd="/tmp/repo")

        assert mock_run.call_args.kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git.subprocess.run")
    def test_empty_output(self, mock_run):
        """Test empty stdout returns '(no commits)'."""
        mock_run.return_value = MagicMock(
            stdout="  \n", stderr="", returncode=0,
        )
        git_log = create_git_log_tool()
        result = git_log()
        assert result == "(no commits)"

    @patch("src.agent.tools.git.subprocess.run")
    def test_error(self, mock_run):
        """Test non-zero return code."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repo", returncode=128,
        )
        git_log = create_git_log_tool()
        result = git_log()

        assert "❌" in result
        assert "not a git repo" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_log = create_git_log_tool()
        result = git_log()

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = OSError("no git")
        git_log = create_git_log_tool()
        result = git_log()

        assert "❌" in result
        assert "no git" in result


# ---------------------------------------------------------------------------
# git_diff
# ---------------------------------------------------------------------------

class TestGitDiffTool:
    """Tests for git_diff tool."""

    @patch("src.agent.tools.git.subprocess.run")
    def test_default_args(self, mock_run):
        """Test default empty args."""
        mock_run.return_value = MagicMock(
            stdout="diff content", stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        result = git_diff()

        assert "git diff " in mock_run.call_args[0][0]
        assert result == "diff content"

    @patch("src.agent.tools.git.subprocess.run")
    def test_staged_diff(self, mock_run):
        """Test staged diff arguments."""
        mock_run.return_value = MagicMock(
            stdout="staged diff", stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        git_diff(args="--staged")

        assert "--staged" in mock_run.call_args[0][0]

    @patch("src.agent.tools.git.subprocess.run")
    def test_no_changes(self, mock_run):
        """Test empty diff returns '(no changes)'."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        result = git_diff()
        assert result == "(no changes)"

    @patch("src.agent.tools.git.subprocess.run")
    def test_truncation_at_20000(self, mock_run):
        """Test diff truncated at 20000 characters."""
        long_diff = "+" * 25000
        mock_run.return_value = MagicMock(
            stdout=long_diff, stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        result = git_diff()

        assert "[Diff truncated at 20,000 characters" in result
        assert len(result) < 25000

    @patch("src.agent.tools.git.subprocess.run")
    def test_not_truncated_under_limit(self, mock_run):
        """Test diff under limit is not truncated."""
        mock_run.return_value = MagicMock(
            stdout="short diff", stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        result = git_diff()
        assert "truncated" not in result.lower()

    @patch("src.agent.tools.git.subprocess.run")
    def test_with_cwd(self, mock_run):
        """Test cwd passed through."""
        mock_run.return_value = MagicMock(
            stdout="ok", stderr="", returncode=0,
        )
        git_diff = create_git_diff_tool()
        git_diff(cwd="/tmp/repo")
        assert mock_run.call_args.kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git.subprocess.run")
    def test_error(self, mock_run):
        """Test non-zero return code."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: bad revision", returncode=128,
        )
        git_diff = create_git_diff_tool()
        result = git_diff(args="nonexistent")

        assert "❌" in result
        assert "bad revision" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_diff = create_git_diff_tool()
        result = git_diff()

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = RuntimeError("unexpected")
        git_diff = create_git_diff_tool()
        result = git_diff()

        assert "❌" in result
        assert "unexpected" in result


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------

class TestGitStatusTool:
    """Tests for git_status tool."""

    @patch("src.agent.tools.git.subprocess.run")
    def test_clean_status(self, mock_run):
        """Test clean working tree."""
        mock_run.return_value = MagicMock(
            stdout="On branch main\nnothing to commit", stderr="", returncode=0,
        )
        git_status = create_git_status_tool()
        result = git_status()

        assert "On branch main" in result
        mock_run.assert_called_once_with(
            "git status",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )

    @patch("src.agent.tools.git.subprocess.run")
    def test_with_cwd(self, mock_run):
        """Test cwd passed through."""
        mock_run.return_value = MagicMock(
            stdout="status", stderr="", returncode=0,
        )
        git_status = create_git_status_tool()
        git_status(cwd="/tmp/repo")
        assert mock_run.call_args.kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git.subprocess.run")
    def test_error(self, mock_run):
        """Test non-zero return code."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repo", returncode=128,
        )
        git_status = create_git_status_tool()
        result = git_status()

        assert "❌" in result
        assert "not a git repo" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_status = create_git_status_tool()
        result = git_status()

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = OSError("no git")
        git_status = create_git_status_tool()
        result = git_status()

        assert "❌" in result
        assert "no git" in result


# ---------------------------------------------------------------------------
# git_add
# ---------------------------------------------------------------------------

class TestGitAddTool:
    """Tests for git_add tool."""

    @patch("src.agent.tools.git.subprocess.run")
    def test_add_single_file(self, mock_run):
        """Test staging a single file."""
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),  # git add
            MagicMock(stdout="M  src/main.py\n", stderr="", returncode=0),  # git status
        ]
        git_add = create_git_add_tool()
        result = git_add("src/main.py")

        assert "✅" in result
        assert "src/main.py" in result
        assert mock_run.call_count == 2

    @patch("src.agent.tools.git.subprocess.run")
    def test_add_all(self, mock_run):
        """Test staging all files."""
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),
            MagicMock(stdout="A  new.py\nM  old.py\n", stderr="", returncode=0),
        ]
        git_add = create_git_add_tool()
        result = git_add(".")

        assert "✅" in result
        assert "Staged files: ." in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_add_with_cwd(self, mock_run):
        """Test cwd is passed to both subprocess calls."""
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),
            MagicMock(stdout="", stderr="", returncode=0),
        ]
        git_add = create_git_add_tool()
        git_add(".", cwd="/tmp/repo")

        assert mock_run.call_args_list[0].kwargs["cwd"] == "/tmp/repo"
        assert mock_run.call_args_list[1].kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git.subprocess.run")
    def test_add_error(self, mock_run):
        """Test git add failure."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: pathspec 'x' did not match any files", returncode=128,
        )
        git_add = create_git_add_tool()
        result = git_add("x")

        assert "❌" in result
        assert "pathspec" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_add = create_git_add_tool()
        result = git_add(".")

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = OSError("disk full")
        git_add = create_git_add_tool()
        result = git_add(".")

        assert "❌" in result
        assert "disk full" in result


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------

class TestGitCommitTool:
    """Tests for git_commit tool."""

    @patch("src.agent.tools.git.subprocess.run")
    def test_successful_commit(self, mock_run):
        """Test successful commit."""
        mock_run.return_value = MagicMock(
            stdout="[main abc1234] Fix bug\n 1 file changed",
            stderr="",
            returncode=0,
        )
        git_commit = create_git_commit_tool()
        result = git_commit("Fix bug")

        assert "✅" in result
        assert "abc1234" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_commit_with_cwd(self, mock_run):
        """Test cwd is passed through."""
        mock_run.return_value = MagicMock(
            stdout="committed", stderr="", returncode=0,
        )
        git_commit = create_git_commit_tool()
        git_commit("msg", cwd="/tmp/repo")
        assert mock_run.call_args.kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git.subprocess.run")
    def test_appends_co_author(self, mock_run):
        """Test Co-Authored-By is included in command."""
        mock_run.return_value = MagicMock(
            stdout="committed", stderr="", returncode=0,
        )
        git_commit = create_git_commit_tool()
        git_commit("Add feature")

        cmd = mock_run.call_args[0][0]
        assert "Co-Authored-By: EchoMind Agent" in cmd

    def test_empty_message(self):
        """Test empty commit message returns error without calling subprocess."""
        git_commit = create_git_commit_tool()
        result = git_commit("")

        assert "❌" in result
        assert "empty" in result.lower()

    def test_whitespace_message(self):
        """Test whitespace-only commit message returns error."""
        git_commit = create_git_commit_tool()
        result = git_commit("   ")

        assert "❌" in result
        assert "empty" in result.lower()

    @patch("src.agent.tools.git.subprocess.run")
    def test_nothing_to_commit(self, mock_run):
        """Test 'nothing to commit' error message."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="nothing to commit, working tree clean",
            returncode=1,
        )
        git_commit = create_git_commit_tool()
        result = git_commit("Update readme")

        assert "❌" in result
        assert "No changes to commit" in result
        assert "git_add" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_user_not_configured(self, mock_run):
        """Test git user not configured error."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="please tell me who you are",
            returncode=128,
        )
        git_commit = create_git_commit_tool()
        result = git_commit("msg")

        assert "❌" in result
        assert "user.name" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_other_error(self, mock_run):
        """Test other git error falls through."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="some unknown error",
            returncode=1,
        )
        git_commit = create_git_commit_tool()
        result = git_commit("msg")

        assert "❌" in result
        assert "some unknown error" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_timeout(self, mock_run):
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_commit = create_git_commit_tool()
        result = git_commit("msg")

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = RuntimeError("unexpected")
        git_commit = create_git_commit_tool()
        result = git_commit("msg")

        assert "❌" in result
        assert "unexpected" in result
