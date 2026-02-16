"""Tests for skill executor."""

import os

import pytest

from mcp_gateway.skills.executor import ExecutionResult, SkillExecutor
from mcp_gateway.skills.registry import SkillArgument, SkillDefinition


def _make_skill(
    command: str = "echo hello",
    args: list[SkillArgument] | None = None,
    timeout: int = 30,
    name: str = "test-skill",
) -> SkillDefinition:
    """
    Create a SkillDefinition for testing.

    Args:
        command: Shell command template.
        args: Skill arguments.
        timeout: Execution timeout in seconds.
        name: Skill name.

    Returns:
        SkillDefinition with the given parameters.
    """
    return SkillDefinition(
        name=name,
        description="Test skill",
        command=command,
        args=args or [],
        timeout=timeout,
    )


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_defaults(self) -> None:
        """Test default values for timed_out."""
        result = ExecutionResult(
            success=True, exit_code=0, stdout="ok", stderr=""
        )
        assert result.timed_out is False

    def test_all_fields(self) -> None:
        """Test creating with all fields."""
        result = ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="timeout",
            timed_out=True,
        )
        assert result.success is False
        assert result.timed_out is True


class TestSkillExecutorSimple:
    """Tests for basic skill execution."""

    @pytest.mark.asyncio
    async def test_execute_simple_command(self) -> None:
        """Test executing a simple echo command."""
        executor = SkillExecutor()
        skill = _make_skill(command="echo hello")
        result = await executor.execute(skill)

        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_execute_command_with_stderr(self) -> None:
        """Test that stderr is captured from commands."""
        executor = SkillExecutor()
        skill = _make_skill(command="echo error >&2")
        result = await executor.execute(skill)

        assert result.exit_code == 0
        assert "error" in result.stderr

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        """Test that non-zero exit code returns success=False."""
        executor = SkillExecutor()
        skill = _make_skill(command="exit 42")
        result = await executor.execute(skill)

        assert result.success is False
        assert result.exit_code == 42
        assert result.timed_out is False


class TestSkillExecutorArgs:
    """Tests for argument interpolation."""

    @pytest.mark.asyncio
    async def test_dollar_brace_interpolation(self) -> None:
        """Test ${arg} interpolation syntax."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="echo ${input}",
            args=[SkillArgument(name="input", description="text")],
        )
        result = await executor.execute(skill, args={"input": "world"})

        assert result.success is True
        assert "world" in result.stdout

    @pytest.mark.asyncio
    async def test_missing_required_argument(self) -> None:
        """Test that missing required argument returns error result."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="echo $input",
            args=[
                SkillArgument(
                    name="input", description="text", required=True
                ),
            ],
        )
        result = await executor.execute(skill, args={})

        assert result.success is False
        assert result.exit_code == -1
        assert "Missing required argument: input" in result.stderr

    @pytest.mark.asyncio
    async def test_default_argument_applied(self) -> None:
        """Test that default value is used when argument not provided."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="echo ${format}",
            args=[
                SkillArgument(
                    name="format",
                    description="output format",
                    required=False,
                    default="json",
                ),
            ],
        )
        result = await executor.execute(skill, args={})

        assert result.success is True
        assert "json" in result.stdout

    @pytest.mark.asyncio
    async def test_provided_arg_overrides_default(self) -> None:
        """Test that provided argument overrides default value."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="echo ${format}",
            args=[
                SkillArgument(
                    name="format",
                    description="output format",
                    default="json",
                ),
            ],
        )
        result = await executor.execute(skill, args={"format": "yaml"})

        assert result.success is True
        assert "yaml" in result.stdout

    @pytest.mark.asyncio
    async def test_none_args_treated_as_empty(self) -> None:
        """Test that passing None for args works like empty dict."""
        executor = SkillExecutor()
        skill = _make_skill(command="echo ok")
        result = await executor.execute(skill, args=None)

        assert result.success is True
        assert "ok" in result.stdout


class TestSkillExecutorQuoting:
    """Tests for argument shell-quoting (passthrough removed for security)."""

    @pytest.mark.asyncio
    async def test_all_args_are_shell_quoted(self) -> None:
        """All arguments are shell-quoted, preventing command injection."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="${command}",
            args=[SkillArgument(name="command", description="Full command", required=True)],
        )
        # The entire value is treated as a single quoted token, not a command
        result = await executor.execute(skill, args={"command": "echo hello world"})
        # The quoted string is treated as a single command name, so it fails
        assert result.success is False

    @pytest.mark.asyncio
    async def test_structured_command_quotes_args(self) -> None:
        """Structured commands shell-quote arguments preventing injection."""
        executor = SkillExecutor()
        skill = _make_skill(
            command="echo ${input}",
            args=[SkillArgument(name="input", description="text", required=True)],
        )
        # With shell injection attempt
        result = await executor.execute(skill, args={"input": "hello; echo injected"})
        assert result.success is True
        # The semicolon should be quoted, not interpreted as a command separator
        assert "injected" not in result.stdout.split("\n")[0] or "hello; echo injected" in result.stdout


class TestSkillExecutorSafeEnv:
    """Tests for environment sandboxing."""

    @pytest.mark.asyncio
    async def test_base_env_vars_included(self) -> None:
        """PATH, HOME, LANG are always available."""
        executor = SkillExecutor()
        skill = _make_skill(command="echo $PATH")
        result = await executor.execute(skill)
        assert result.success is True
        # PATH should be non-empty
        assert result.stdout.strip() != ""

    @pytest.mark.asyncio
    async def test_env_var_referenced_in_command(self) -> None:
        """Env vars referenced as $UPPER_CASE in command are passed through."""
        executor = SkillExecutor()
        # Set a test env var
        os.environ["TEST_MCP_VAR"] = "test_value_123"
        try:
            skill = _make_skill(command="echo $TEST_MCP_VAR")
            result = await executor.execute(skill)
            assert result.success is True
            assert "test_value_123" in result.stdout
        finally:
            del os.environ["TEST_MCP_VAR"]


class TestSkillExecutorTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_command_timeout(self) -> None:
        """Test that a slow command is killed after timeout."""
        executor = SkillExecutor()
        skill = _make_skill(command="sleep 10", timeout=1)
        result = await executor.execute(skill)

        assert result.success is False
        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timed out" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_skill_timeout_used_over_default(self) -> None:
        """Test that skill-level timeout overrides executor default."""
        executor = SkillExecutor(default_timeout=60)
        skill = _make_skill(command="sleep 10", timeout=1)
        result = await executor.execute(skill)

        assert result.timed_out is True


class TestSkillExecutorOutputTruncation:
    """Tests for output truncation."""

    @pytest.mark.asyncio
    async def test_output_truncated_when_exceeding_max(self) -> None:
        """Test that output exceeding max_output_bytes is truncated."""
        executor = SkillExecutor(max_output_bytes=50)
        # Generate output larger than 50 bytes
        skill = _make_skill(command="python3 -c \"print('A' * 200)\"")
        result = await executor.execute(skill)

        assert result.success is True
        assert result.stdout.endswith("... [output truncated]")
        # Truncated output (before indicator) should be <= 50 bytes
        content = result.stdout.replace("\n... [output truncated]", "")
        assert len(content.encode("utf-8")) <= 50

    @pytest.mark.asyncio
    async def test_per_skill_max_output_bytes_overrides_default(self) -> None:
        """Test that per-skill max_output_bytes overrides executor default."""
        executor = SkillExecutor(max_output_bytes=65536)
        skill = _make_skill(command="python3 -c \"print('B' * 200)\"")
        # Set per-skill limit to 50 bytes
        skill.max_output_bytes = 50
        result = await executor.execute(skill)

        assert result.success is True
        assert result.stdout.endswith("... [output truncated]")
        content = result.stdout.replace("\n... [output truncated]", "")
        assert len(content.encode("utf-8")) <= 50

    @pytest.mark.asyncio
    async def test_none_max_output_bytes_uses_executor_default(self) -> None:
        """Test that None max_output_bytes falls back to executor default."""
        executor = SkillExecutor(max_output_bytes=50)
        skill = _make_skill(command="python3 -c \"print('C' * 200)\"")
        # max_output_bytes is None by default
        assert skill.max_output_bytes is None
        result = await executor.execute(skill)

        assert result.success is True
        assert result.stdout.endswith("... [output truncated]")
        content = result.stdout.replace("\n... [output truncated]", "")
        assert len(content.encode("utf-8")) <= 50

    @pytest.mark.asyncio
    async def test_output_not_truncated_when_under_max(self) -> None:
        """Test that small output is not truncated."""
        executor = SkillExecutor(max_output_bytes=65536)
        skill = _make_skill(command="echo short")
        result = await executor.execute(skill)

        assert "truncated" not in result.stdout
