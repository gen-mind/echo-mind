"""
Execution tools for agent system.

Provides safe command execution with proper timeouts and error handling.
All tools follow FAANG principal engineer quality standards.

Confidence: High - Tools match Moltbot implementations
"""

import subprocess
from collections.abc import Callable
from typing import Annotated

from pydantic import Field


def create_bash_tool() -> Callable[..., str]:
    """
    Create tool for executing bash commands.

    Returns:
        Callable that executes bash commands and returns output.
    """

    def bash(
        command: Annotated[str, Field(description="Bash command to execute")],
        timeout: Annotated[
            int, Field(description="Timeout in seconds", gt=0, le=300)
        ] = 30,
    ) -> str:
        """
        Execute a bash command and return output.

        Args:
            command: Bash command to execute
            timeout: Maximum execution time in seconds (max 300)

        Returns:
            Command output (stdout + stderr) or error message

        Security:
            - Commands run in shell (use with caution)
            - Timeout enforced to prevent infinite loops
            - No directory restrictions (use sandbox for production)
        """
        try:
            if not command.strip():
                return "❌ Error: Command cannot be empty"

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Combine stdout and stderr
            output = result.stdout

            if result.stderr:
                output += f"\n\n[stderr]\n{result.stderr}"

            if result.returncode != 0:
                output += f"\n\n[Exit code: {result.returncode}]"

            # Truncate if too long (> 10000 characters)
            max_length = 10000
            if len(output) > max_length:
                output = (
                    output[:max_length]
                    + f"\n\n[Output truncated at {max_length:,} characters]"
                )

            return output if output.strip() else "(no output)"

        except subprocess.TimeoutExpired:
            return f"❌ Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"❌ Error executing command: {str(e)}"

    return bash
