"""
Skill executor for running skill commands via subprocess.

Handles command interpolation, timeout enforcement, and output capture.
"""

import logging
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from mcp_gateway.skills.registry import SkillDefinition

logger = logging.getLogger("echomind-mcp-gateway")


@dataclass
class ExecutionResult:
    """Result of a skill execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SkillExecutor:
    """
    Executes skill commands via subprocess.

    Provides timeout enforcement, output size limits,
    and argument interpolation for skill commands.
    """

    def __init__(
        self,
        default_timeout: int = 30,
        max_output_bytes: int = 65536,
    ) -> None:
        """
        Initialize skill executor.

        Args:
            default_timeout: Default execution timeout in seconds.
            max_output_bytes: Maximum output size in bytes (stdout + stderr).
        """
        self._default_timeout = default_timeout
        self._max_output_bytes = max_output_bytes

    def execute(
        self,
        skill: SkillDefinition,
        args: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """
        Execute a skill command.

        Interpolates arguments into the command template,
        runs via subprocess with timeout, and captures output.

        Args:
            skill: The skill definition to execute.
            args: Key-value arguments to interpolate into the command.

        Returns:
            ExecutionResult with stdout, stderr, exit code, and timeout status.
        """
        args = args or {}

        # Validate required arguments
        for arg_def in skill.args:
            if arg_def.required and arg_def.name not in args:
                return ExecutionResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Missing required argument: {arg_def.name}",
                )

        # Apply defaults for missing optional args
        full_args = {}
        for arg_def in skill.args:
            if arg_def.name in args:
                full_args[arg_def.name] = args[arg_def.name]
            elif arg_def.default is not None:
                full_args[arg_def.name] = arg_def.default

        # Interpolate arguments into command
        command = skill.command
        for key, value in full_args.items():
            # Use shell-safe quoting for interpolated values
            safe_value = shlex.quote(str(value))
            command = command.replace(f"${{{key}}}", safe_value)
            command = command.replace(f"${key}", safe_value)

        timeout = skill.timeout or self._default_timeout

        logger.info(f"🚀 Executing skill '{skill.name}' (timeout: {timeout}s)")
        logger.debug(f"   Command: {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=None,
                env=None,  # Inherit parent environment
            )

            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)

            success = result.returncode == 0
            if success:
                logger.info(f"✅ Skill '{skill.name}' completed (exit code: {result.returncode})")
            else:
                logger.warning(
                    f"⚠️ Skill '{skill.name}' failed (exit code: {result.returncode})"
                )

            return ExecutionResult(
                success=success,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )

        except subprocess.TimeoutExpired:
            logger.error(f"⏰ Skill '{skill.name}' timed out after {timeout}s")
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                timed_out=True,
            )
        except Exception as e:
            logger.error(f"❌ Skill '{skill.name}' execution error: {e}")
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
            )

    def _truncate_output(self, output: str) -> str:
        """
        Truncate output to max size.

        Args:
            output: Raw output string.

        Returns:
            Truncated output with indicator if truncated.
        """
        if len(output.encode("utf-8")) > self._max_output_bytes:
            truncated = output.encode("utf-8")[:self._max_output_bytes].decode(
                "utf-8", errors="ignore"
            )
            return truncated + "\n... [output truncated]"
        return output
