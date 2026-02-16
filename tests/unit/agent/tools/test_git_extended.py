"""
Unit tests for extended git tools.

Tests cover git_branch, git_checkout, git_stash, git_push, git_pull,
git_reset, git_clone, and git_tag tools.
All subprocess.run calls are mocked — no real git commands are executed.
Target: 100% code coverage
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.git_extended import (
    create_git_branch_tool,
    create_git_checkout_tool,
    create_git_clone_tool,
    create_git_pull_tool,
    create_git_push_tool,
    create_git_reset_tool,
    create_git_stash_tool,
    create_git_tag_tool,
)


# ---------------------------------------------------------------------------
# git_branch
# ---------------------------------------------------------------------------


class TestGitBranchTool:
    """Tests for git_branch tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_list(self, mock_run: MagicMock) -> None:
        """Test listing branches."""
        mock_run.return_value = MagicMock(
            stdout="* main\n  develop\n", stderr="", returncode=0,
        )
        git_branch = create_git_branch_tool()
        result = git_branch(action="list")

        mock_run.assert_called_once_with(
            "git branch -a",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "main" in result
        assert "develop" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_create(self, mock_run: MagicMock) -> None:
        """Test creating a branch."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        git_branch = create_git_branch_tool()
        result = git_branch(action="create", name="feature/new")

        mock_run.assert_called_once_with(
            "git branch feature/new",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert result == "(no output)"

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_delete(self, mock_run: MagicMock) -> None:
        """Test deleting a branch (safe delete -d, not -D)."""
        mock_run.return_value = MagicMock(
            stdout="Deleted branch feature/old\n", stderr="", returncode=0,
        )
        git_branch = create_git_branch_tool()
        result = git_branch(action="delete", name="feature/old")

        cmd = mock_run.call_args[0][0]
        assert "git branch -d feature/old" in cmd
        assert "-D" not in cmd
        assert "Deleted" in result

    def test_git_branch_invalid_action(self) -> None:
        """Test invalid action returns error without calling subprocess."""
        git_branch = create_git_branch_tool()
        result = git_branch(action="force-delete")

        assert "❌" in result
        assert "Invalid action" in result

    def test_git_branch_create_no_name(self) -> None:
        """Test create without name returns error."""
        git_branch = create_git_branch_tool()
        result = git_branch(action="create")

        assert "❌" in result
        assert "name is required" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_with_cwd(self, mock_run: MagicMock) -> None:
        """Test cwd is passed through."""
        mock_run.return_value = MagicMock(
            stdout="* main\n", stderr="", returncode=0,
        )
        git_branch = create_git_branch_tool()
        git_branch(action="list", cwd="/tmp/repo")

        assert mock_run.call_args.kwargs["cwd"] == "/tmp/repo"

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_branch = create_git_branch_tool()
        result = git_branch(action="list")

        assert "❌" in result
        assert "timed out" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_branch_error(self, mock_run: MagicMock) -> None:
        """Test non-zero return code."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repo", returncode=128,
        )
        git_branch = create_git_branch_tool()
        result = git_branch(action="list")

        assert "❌" in result
        assert "not a git repo" in result


# ---------------------------------------------------------------------------
# git_checkout
# ---------------------------------------------------------------------------


class TestGitCheckoutTool:
    """Tests for git_checkout tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_checkout_branch(self, mock_run: MagicMock) -> None:
        """Test switching to existing branch."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Switched to branch 'develop'\n", returncode=0,
        )
        git_checkout = create_git_checkout_tool()
        result = git_checkout(target="develop")

        mock_run.assert_called_once_with(
            "git checkout develop",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Switched" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_checkout_create_branch(self, mock_run: MagicMock) -> None:
        """Test creating and switching to new branch."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Switched to a new branch 'feature/x'\n", returncode=0,
        )
        git_checkout = create_git_checkout_tool()
        result = git_checkout(target="feature/x", create_branch=True)

        cmd = mock_run.call_args[0][0]
        assert "git checkout -b feature/x" in cmd
        assert "new branch" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_checkout_error(self, mock_run: MagicMock) -> None:
        """Test checkout error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="error: pathspec 'nope' did not match", returncode=1,
        )
        git_checkout = create_git_checkout_tool()
        result = git_checkout(target="nope")

        assert "❌" in result
        assert "pathspec" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_checkout_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_checkout = create_git_checkout_tool()
        result = git_checkout(target="main")

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_stash
# ---------------------------------------------------------------------------


class TestGitStashTool:
    """Tests for git_stash tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_push(self, mock_run: MagicMock) -> None:
        """Test stash push without message."""
        mock_run.return_value = MagicMock(
            stdout="Saved working directory\n", stderr="", returncode=0,
        )
        git_stash = create_git_stash_tool()
        result = git_stash(action="push")

        mock_run.assert_called_once_with(
            "git stash push",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Saved" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_push_with_message(self, mock_run: MagicMock) -> None:
        """Test stash push with message."""
        mock_run.return_value = MagicMock(
            stdout="Saved working directory\n", stderr="", returncode=0,
        )
        git_stash = create_git_stash_tool()
        git_stash(action="push", message="WIP: feature")

        cmd = mock_run.call_args[0][0]
        assert 'git stash push -m "WIP: feature"' in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_pop(self, mock_run: MagicMock) -> None:
        """Test stash pop."""
        mock_run.return_value = MagicMock(
            stdout="On branch main\nChanges restored\n", stderr="", returncode=0,
        )
        git_stash = create_git_stash_tool()
        result = git_stash(action="pop")

        mock_run.assert_called_once_with(
            "git stash pop",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "restored" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_list(self, mock_run: MagicMock) -> None:
        """Test stash list."""
        mock_run.return_value = MagicMock(
            stdout="stash@{0}: WIP on main\n", stderr="", returncode=0,
        )
        git_stash = create_git_stash_tool()
        result = git_stash(action="list")

        mock_run.assert_called_once_with(
            "git stash list",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "stash@{0}" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_drop(self, mock_run: MagicMock) -> None:
        """Test stash drop."""
        mock_run.return_value = MagicMock(
            stdout="Dropped refs/stash@{0}\n", stderr="", returncode=0,
        )
        git_stash = create_git_stash_tool()
        result = git_stash(action="drop")

        mock_run.assert_called_once_with(
            "git stash drop",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Dropped" in result

    def test_git_stash_invalid_action(self) -> None:
        """Test invalid action returns error."""
        git_stash = create_git_stash_tool()
        result = git_stash(action="apply")

        assert "❌" in result
        assert "Invalid action" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_stash_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_stash = create_git_stash_tool()
        result = git_stash(action="push")

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_push
# ---------------------------------------------------------------------------


class TestGitPushTool:
    """Tests for git_push tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_push_basic(self, mock_run: MagicMock) -> None:
        """Test basic push to origin."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Everything up-to-date\n", returncode=0,
        )
        git_push = create_git_push_tool()
        result = git_push()

        mock_run.assert_called_once_with(
            "git push origin",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "up-to-date" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_push_with_upstream(self, mock_run: MagicMock) -> None:
        """Test push with --set-upstream."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Branch 'feature' set up to track\n", returncode=0,
        )
        git_push = create_git_push_tool()
        git_push(branch="feature", set_upstream=True)

        cmd = mock_run.call_args[0][0]
        assert "git push origin feature --set-upstream" in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_push_force_with_lease(self, mock_run: MagicMock) -> None:
        """Test push with --force-with-lease (safe force)."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="forced update\n", returncode=0,
        )
        git_push = create_git_push_tool()
        git_push(force_with_lease=True)

        cmd = mock_run.call_args[0][0]
        assert "--force-with-lease" in cmd
        assert "--force " not in cmd  # Never bare --force

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_push_error(self, mock_run: MagicMock) -> None:
        """Test push error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="rejected: non-fast-forward", returncode=1,
        )
        git_push = create_git_push_tool()
        result = git_push()

        assert "❌" in result
        assert "rejected" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_push_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_push = create_git_push_tool()
        result = git_push()

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_pull
# ---------------------------------------------------------------------------


class TestGitPullTool:
    """Tests for git_pull tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_pull_basic(self, mock_run: MagicMock) -> None:
        """Test basic pull from origin."""
        mock_run.return_value = MagicMock(
            stdout="Already up to date.\n", stderr="", returncode=0,
        )
        git_pull = create_git_pull_tool()
        result = git_pull()

        mock_run.assert_called_once_with(
            "git pull origin",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Already up to date" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_pull_with_branch(self, mock_run: MagicMock) -> None:
        """Test pull with specific branch."""
        mock_run.return_value = MagicMock(
            stdout="Updating abc..def\n", stderr="", returncode=0,
        )
        git_pull = create_git_pull_tool()
        git_pull(remote="upstream", branch="main")

        cmd = mock_run.call_args[0][0]
        assert "git pull upstream main" in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_pull_error(self, mock_run: MagicMock) -> None:
        """Test pull error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: refusing to merge unrelated histories", returncode=128,
        )
        git_pull = create_git_pull_tool()
        result = git_pull()

        assert "❌" in result
        assert "unrelated histories" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_pull_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_pull = create_git_pull_tool()
        result = git_pull()

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_reset
# ---------------------------------------------------------------------------


class TestGitResetTool:
    """Tests for git_reset tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_reset_mixed(self, mock_run: MagicMock) -> None:
        """Test mixed reset (allowed)."""
        mock_run.return_value = MagicMock(
            stdout="Unstaged changes after reset:\nM\tsrc/main.py\n",
            stderr="", returncode=0,
        )
        git_reset = create_git_reset_tool()
        result = git_reset(files="src/main.py")

        mock_run.assert_called_once_with(
            "git reset --mixed src/main.py",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Unstaged" in result

    def test_git_reset_hard_rejected(self) -> None:
        """Test hard reset is blocked for safety (CRITICAL)."""
        git_reset = create_git_reset_tool()
        result = git_reset(mode="hard")

        assert "❌" in result
        assert "Only --mixed reset is allowed" in result
        assert "git checkout" in result

    def test_git_reset_soft_rejected(self) -> None:
        """Test soft reset is also blocked."""
        git_reset = create_git_reset_tool()
        result = git_reset(mode="soft")

        assert "❌" in result
        assert "Only --mixed reset is allowed" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_reset_error(self, mock_run: MagicMock) -> None:
        """Test reset error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: not a git repo", returncode=128,
        )
        git_reset = create_git_reset_tool()
        result = git_reset()

        assert "❌" in result
        assert "not a git repo" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_reset_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_reset = create_git_reset_tool()
        result = git_reset()

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_clone
# ---------------------------------------------------------------------------


class TestGitCloneTool:
    """Tests for git_clone tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_clone_basic(self, mock_run: MagicMock) -> None:
        """Test basic clone."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Cloning into 'repo'...\n", returncode=0,
        )
        git_clone = create_git_clone_tool()
        result = git_clone(url="https://github.com/user/repo.git")

        mock_run.assert_called_once_with(
            "git clone https://github.com/user/repo.git",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Cloning" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_clone_with_depth(self, mock_run: MagicMock) -> None:
        """Test shallow clone with depth."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Cloning into 'repo'...\n", returncode=0,
        )
        git_clone = create_git_clone_tool()
        git_clone(url="https://github.com/user/repo.git", depth=1)

        cmd = mock_run.call_args[0][0]
        assert "--depth 1" in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_clone_with_directory(self, mock_run: MagicMock) -> None:
        """Test clone into specific directory."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="Cloning into 'mydir'...\n", returncode=0,
        )
        git_clone = create_git_clone_tool()
        git_clone(url="https://github.com/user/repo.git", directory="mydir")

        cmd = mock_run.call_args[0][0]
        assert "mydir" in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_clone_error(self, mock_run: MagicMock) -> None:
        """Test clone error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: repository not found", returncode=128,
        )
        git_clone = create_git_clone_tool()
        result = git_clone(url="https://github.com/user/nope.git")

        assert "❌" in result
        assert "repository not found" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_clone_timeout(self, mock_run: MagicMock) -> None:
        """Test timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        git_clone = create_git_clone_tool()
        result = git_clone(url="https://github.com/user/repo.git")

        assert "❌" in result
        assert "timed out" in result


# ---------------------------------------------------------------------------
# git_tag
# ---------------------------------------------------------------------------


class TestGitTagTool:
    """Tests for git_tag tool."""

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_list(self, mock_run: MagicMock) -> None:
        """Test listing tags."""
        mock_run.return_value = MagicMock(
            stdout="v1.0.0\nv1.1.0\n", stderr="", returncode=0,
        )
        git_tag = create_git_tag_tool()
        result = git_tag(action="list")

        mock_run.assert_called_once_with(
            "git tag -l",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "v1.0.0" in result
        assert "v1.1.0" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_create(self, mock_run: MagicMock) -> None:
        """Test creating lightweight tag."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        git_tag = create_git_tag_tool()
        result = git_tag(action="create", name="v2.0.0")

        mock_run.assert_called_once_with(
            "git tag v2.0.0",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert result == "(no output)"

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_create_annotated(self, mock_run: MagicMock) -> None:
        """Test creating annotated tag with message."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        git_tag = create_git_tag_tool()
        git_tag(action="create", name="v2.0.0", message="Release 2.0")

        cmd = mock_run.call_args[0][0]
        assert 'git tag -a v2.0.0 -m "Release 2.0"' in cmd

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_delete(self, mock_run: MagicMock) -> None:
        """Test deleting tag."""
        mock_run.return_value = MagicMock(
            stdout="Deleted tag 'v1.0.0'\n", stderr="", returncode=0,
        )
        git_tag = create_git_tag_tool()
        result = git_tag(action="delete", name="v1.0.0")

        mock_run.assert_called_once_with(
            "git tag -d v1.0.0",
            shell=True, capture_output=True, text=True, timeout=30, cwd=None,
        )
        assert "Deleted" in result

    def test_git_tag_invalid_action(self) -> None:
        """Test invalid action returns error."""
        git_tag = create_git_tag_tool()
        result = git_tag(action="push")

        assert "❌" in result
        assert "Invalid action" in result

    def test_git_tag_create_no_name(self) -> None:
        """Test create without name returns error."""
        git_tag = create_git_tag_tool()
        result = git_tag(action="create")

        assert "❌" in result
        assert "name is required" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_error(self, mock_run: MagicMock) -> None:
        """Test tag error."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="fatal: tag 'v1.0.0' already exists", returncode=128,
        )
        git_tag = create_git_tag_tool()
        result = git_tag(action="create", name="v1.0.0")

        assert "❌" in result
        assert "already exists" in result

    @patch("src.agent.tools.git_extended.subprocess.run")
    def test_git_tag_generic_exception(self, mock_run: MagicMock) -> None:
        """Test generic exception handling."""
        mock_run.side_effect = OSError("disk error")
        git_tag = create_git_tag_tool()
        result = git_tag(action="list")

        assert "❌" in result
        assert "disk error" in result
