"""
Skill executor for running skill commands via asyncio subprocess.

Handles command interpolation, timeout enforcement, and output capture.
"""

import asyncio
import logging
import os
import re
import shlex
import signal
from dataclasses import dataclass

from mcp_gateway.skills.registry import SkillDefinition

logger = logging.getLogger("echomind-mcp-gateway")

# Base environment variables always included in subprocess env
_BASE_ENV_KEYS = ("PATH", "HOME", "LANG")

# Environment variable name patterns that must never be passed to subprocesses
_SENSITIVE_PATTERNS = frozenset(
    {"KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL", "DATABASE_URL"}
)


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

    async def execute(
        self,
        skill: SkillDefinition,
        args: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """
        Execute a skill command asynchronously.

        Interpolates arguments into the command template,
        runs via asyncio subprocess with timeout, and captures output.

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
        full_args: dict[str, str] = {}
        for arg_def in skill.args:
            if arg_def.name in args:
                full_args[arg_def.name] = args[arg_def.name]
            elif arg_def.default is not None:
                full_args[arg_def.name] = arg_def.default

        # Interpolate arguments into command with shell-safe quoting
        command = skill.command
        for key, value in full_args.items():
            safe_value = shlex.quote(str(value))
            command = command.replace(f"${{{key}}}", safe_value)

        timeout = skill.timeout or self._default_timeout
        safe_env = self._build_safe_env(skill.command)

        logger.info(f"🚀 Executing skill '{skill.name}' (timeout: {timeout}s)")
        logger.debug(f"   Command: {command[:200]}...")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                env=safe_env,
                cwd="/tmp",
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                self._kill_process_group(process)
                await process.wait()
                logger.error(f"⏰ Skill '{skill.name}' timed out after {timeout}s")
                return ExecutionResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    timed_out=True,
                )

            max_bytes = skill.max_output_bytes or self._max_output_bytes
            stdout = self._truncate_output(
                stdout_bytes.decode("utf-8", errors="replace"), max_bytes
            )
            stderr = self._truncate_output(
                stderr_bytes.decode("utf-8", errors="replace"), max_bytes
            )

            returncode = process.returncode or 0
            success = returncode == 0
            if success:
                logger.info(f"✅ Skill '{skill.name}' completed (exit code: {returncode})")
            else:
                logger.warning(
                    f"⚠️ Skill '{skill.name}' failed (exit code: {returncode})"
                )

            return ExecutionResult(
                success=success,
                exit_code=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:
            logger.error(f"❌ Skill '{skill.name}' execution error: {e}")
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
            )

    def _build_safe_env(self, command: str) -> dict[str, str]:
        """
        Build a restricted environment dict for subprocess execution.

        Includes only PATH, HOME, LANG and any env vars explicitly
        referenced in the command template (``$ENV_VAR`` patterns that
        are NOT ``${arg}`` placeholders).

        Args:
            command: The raw command template string.

        Returns:
            Dict of environment variables safe for subprocess use.
        """
        env: dict[str, str] = {}

        # Always include base keys
        for key in _BASE_ENV_KEYS:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value

        # Find env var references in the command that are NOT ${arg} placeholders
        # Match $UPPER_CASE_VAR patterns (env vars are conventionally uppercase)
        for match in re.finditer(r'\$([A-Z_][A-Z0-9_]*)', command):
            var_name = match.group(1)
            # Skip sensitive env vars to prevent secret leakage
            if any(pattern in var_name for pattern in _SENSITIVE_PATTERNS):
                logger.debug(f"🔒 Skipping sensitive env var: {var_name}")
                continue
            value = os.environ.get(var_name)
            if value is not None:
                env[var_name] = value

        return env

    @staticmethod
    def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        """
        Kill a process and its entire process group.

        Args:
            process: The asyncio subprocess to kill.
        """
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            # Process already exited
            pass

    def _truncate_output(self, output: str, max_bytes: int) -> str:
        """
        Truncate output to max size.

        Args:
            output: Raw output string.
            max_bytes: Maximum output size in bytes.

        Returns:
            Truncated output with indicator if truncated.
        """
        if len(output.encode("utf-8")) > max_bytes:
            truncated = output.encode("utf-8")[:max_bytes].decode(
                "utf-8", errors="ignore"
            )
            return truncated + "\n... [output truncated]"
        return output
