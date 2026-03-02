"""
Unit tests for execution tools (bash).

Tests cover command execution, timeouts, error handling, and output truncation.
All subprocess.run calls are mocked — no real commands are executed.
Target: 100% code coverage
"""

from unittest.mock import patch, MagicMock
import subprocess

import pytest

from src.agent.tools.execution import create_bash_tool


class TestBashToolCreation:
    """Tests for create_bash_tool factory."""

    def test_returns_callable(self):
        """Test that create_bash_tool returns a callable."""
        tool = create_bash_tool()
        assert callable(tool)

    def test_function_name(self):
        """Test the returned function has correct name."""
        tool = create_bash_tool()
        assert tool.__name__ == "bash"


class TestBashToolSuccess:
    """Tests for successful command execution."""

    @patch("src.agent.tools.execution.subprocess.run")
    def test_simple_command(self, mock_run):
        """Test simple command with stdout output."""
        mock_run.return_value = MagicMock(
            stdout="hello world\n",
            stderr="",
            returncode=0,
        )
        bash = create_bash_tool()
        result = bash("echo hello world")

        assert result == "hello world\n"
        mock_run.assert_called_once_with(
            "echo hello world",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("src.agent.tools.execution.subprocess.run")
    def test_custom_timeout(self, mock_run):
        """Test command with custom timeout."""
        mock_run.return_value = MagicMock(
            stdout="ok", stderr="", returncode=0,
        )
        bash = create_bash_tool()
        bash("sleep 1", timeout=60)

        mock_run.assert_called_once_with(
            "sleep 1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    @patch("src.agent.tools.execution.subprocess.run")
    def test_no_output(self, mock_run):
        """Test command with no output returns placeholder."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        bash = create_bash_tool()
        result = bash("true")
        assert result == "(no output)"

    @patch("src.agent.tools.execution.subprocess.run")
    def test_whitespace_only_output(self, mock_run):
        """Test command with whitespace-only output returns placeholder."""
        mock_run.return_value = MagicMock(
            stdout="   \n  ", stderr="", returncode=0,
        )
        bash = create_bash_tool()
        result = bash("echo")
        assert result == "(no output)"


class TestBashToolStderr:
    """Tests for stderr handling."""

    @patch("src.agent.tools.execution.subprocess.run")
    def test_stderr_appended(self, mock_run):
        """Test that stderr is appended to output."""
        mock_run.return_value = MagicMock(
            stdout="out",
            stderr="warning here",
            returncode=0,
        )
        bash = create_bash_tool()
        result = bash("cmd")

        assert "out" in result
        assert "[stderr]" in result
        assert "warning here" in result

    @patch("src.agent.tools.execution.subprocess.run")
    def test_nonzero_exit_code(self, mock_run):
        """Test that non-zero exit code is shown."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="error msg",
            returncode=1,
        )
        bash = create_bash_tool()
        result = bash("false")

        assert "[Exit code: 1]" in result
        assert "error msg" in result

    @patch("src.agent.tools.execution.subprocess.run")
    def test_nonzero_exit_code_with_stdout(self, mock_run):
        """Test non-zero exit with both stdout and stderr."""
        mock_run.return_value = MagicMock(
            stdout="partial output",
            stderr="then error",
            returncode=2,
        )
        bash = create_bash_tool()
        result = bash("bad_cmd")

        assert "partial output" in result
        assert "[stderr]" in result
        assert "then error" in result
        assert "[Exit code: 2]" in result


class TestBashToolTruncation:
    """Tests for output truncation."""

    @patch("src.agent.tools.execution.subprocess.run")
    def test_output_truncated_at_10000(self, mock_run):
        """Test that output exceeding 10000 chars is truncated."""
        long_output = "x" * 15000
        mock_run.return_value = MagicMock(
            stdout=long_output,
            stderr="",
            returncode=0,
        )
        bash = create_bash_tool()
        result = bash("long_cmd")

        assert len(result) < 15000
        assert "[Output truncated at 10,000 characters]" in result
        assert result.startswith("x" * 100)

    @patch("src.agent.tools.execution.subprocess.run")
    def test_output_not_truncated_under_limit(self, mock_run):
        """Test that output under 10000 chars is not truncated."""
        output = "x" * 5000
        mock_run.return_value = MagicMock(
            stdout=output, stderr="", returncode=0,
        )
        bash = create_bash_tool()
        result = bash("cmd")

        assert "truncated" not in result


class TestBashToolErrors:
    """Tests for error handling."""

    def test_empty_command(self):
        """Test empty command returns error without calling subprocess."""
        bash = create_bash_tool()
        result = bash("")
        assert "❌" in result
        assert "empty" in result.lower()

    def test_whitespace_command(self):
        """Test whitespace-only command returns error."""
        bash = create_bash_tool()
        result = bash("   ")
        assert "❌" in result
        assert "empty" in result.lower()

    @patch("src.agent.tools.execution.subprocess.run")
    def test_timeout_expired(self, mock_run):
        """Test TimeoutExpired exception handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=30)
        bash = create_bash_tool()
        result = bash("sleep 999", timeout=30)

        assert "❌" in result
        assert "timed out" in result
        assert "30" in result

    @patch("src.agent.tools.execution.subprocess.run")
    def test_generic_exception(self, mock_run):
        """Test generic exception handling."""
        mock_run.side_effect = OSError("Permission denied")
        bash = create_bash_tool()
        result = bash("restricted_cmd")

        assert "❌" in result
        assert "Permission denied" in result
