"""Skills tools for MCP Gateway."""

import logging
from typing import Any

from fastmcp import FastMCP

from mcp_gateway.skills.exceptions import SkillExecutionError, SkillNotFoundError, SkillTimeoutError
from mcp_gateway.skills.executor import SkillExecutor
from mcp_gateway.skills.registry import SkillRegistry

logger = logging.getLogger("echomind-mcp-gateway")


def register_skills_tools(
    mcp: FastMCP,
    registry: SkillRegistry,
    executor: SkillExecutor,
) -> None:
    """
    Register skills-related MCP tools.

    Args:
        mcp: FastMCP server instance.
        registry: Skill registry with loaded skills.
        executor: Skill executor for running commands.
    """

    @mcp.tool()
    async def skills_list() -> list[dict[str, Any]]:
        """
        List all available skills.

        Returns a list of skill definitions including name,
        description, arguments, and tags.

        Returns:
            List of skill summaries.
        """
        logger.info("📋 skills_list")
        return registry.list_skills()

    @mcp.tool()
    async def skills_get_info(name: str) -> dict[str, Any]:
        """
        Get detailed information about a specific skill.

        Args:
            name: Name of the skill.

        Returns:
            Skill details including documentation.

        Raises:
            ValueError: If skill is not found.
        """
        logger.info(f"ℹ️ skills_get_info: name='{name}'")
        skill = registry.get_skill(name)
        if skill is None:
            raise SkillNotFoundError(f"Skill '{name}' not found")
        return {
            "name": skill.name,
            "description": skill.description,
            "args": [
                {
                    "name": a.name,
                    "description": a.description,
                    "required": a.required,
                    "default": a.default,
                }
                for a in skill.args
            ],
            "tags": skill.tags,
            "timeout": skill.timeout,
            "max_output_bytes": skill.max_output_bytes,
            "documentation": skill.documentation,
        }

    @mcp.tool()
    async def skills_execute(
        name: str,
        args: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a skill by name with optional arguments.

        Runs the skill's command via subprocess with timeout enforcement.

        Args:
            name: Name of the skill to execute.
            args: Key-value arguments for the skill command.

        Returns:
            Execution result with stdout, stderr, exit_code, and success status.

        Raises:
            ValueError: If skill is not found.
        """
        logger.info(f"🚀 skills_execute: name='{name}', args={args}")
        skill = registry.get_skill(name)
        if skill is None:
            raise SkillNotFoundError(f"Skill '{name}' not found")

        result = await executor.execute(skill, args)

        if result.timed_out:
            raise SkillTimeoutError(
                f"Skill '{name}' timed out after {skill.timeout}s"
            )

        if not result.success:
            raise SkillExecutionError(
                f"Skill '{name}' failed (exit_code={result.exit_code}): "
                f"{result.stderr[:200] if result.stderr else 'no output'}"
            )

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }
