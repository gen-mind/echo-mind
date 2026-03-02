"""Unit tests for mcp_gateway.tools.skills."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_gateway.skills.exceptions import SkillExecutionError, SkillNotFoundError, SkillTimeoutError
from mcp_gateway.skills.executor import ExecutionResult
from mcp_gateway.skills.registry import SkillArgument, SkillDefinition
from mcp_gateway.tools.skills import register_skills_tools


def _make_skill(
    name: str = "test-skill",
    description: str = "A test skill",
    command: str = "echo hello",
    args: list[SkillArgument] | None = None,
    tags: list[str] | None = None,
    timeout: int = 30,
    documentation: str = "Some docs",
) -> SkillDefinition:
    """Helper to create a SkillDefinition for testing."""
    return SkillDefinition(
        name=name,
        description=description,
        command=command,
        args=args or [],
        tags=tags or [],
        timeout=timeout,
        documentation=documentation,
    )


@pytest.fixture
def mock_registry() -> MagicMock:
    """Create a mock SkillRegistry."""
    registry = MagicMock()
    registry.list_skills = MagicMock(return_value=[])
    registry.get_skill = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_executor() -> MagicMock:
    """Create a mock SkillExecutor."""
    executor = MagicMock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture
def tool_functions(
    mock_registry: MagicMock, mock_executor: MagicMock
) -> dict[str, Any]:
    """
    Register skills tools and capture the inner tool functions.

    Returns a dict mapping tool name to the async callable.
    """
    captured: dict[str, Any] = {}

    class FakeMCP:
        """Fake FastMCP that captures tool registrations."""

        def tool(self) -> Any:
            """Return decorator that captures the function."""
            def decorator(fn: Any) -> Any:
                captured[fn.__name__] = fn
                return fn
            return decorator

    fake_mcp = FakeMCP()
    register_skills_tools(fake_mcp, mock_registry, mock_executor)  # type: ignore[arg-type]
    return captured


class TestRegisterSkillsTools:
    """Tests for register_skills_tools registration."""

    def test_registers_three_tools(self, tool_functions: dict[str, Any]) -> None:
        """Verify all three skills tools are registered."""
        assert "skills_list" in tool_functions
        assert "skills_get_info" in tool_functions
        assert "skills_execute" in tool_functions

    def test_registers_exactly_three(self, tool_functions: dict[str, Any]) -> None:
        """Verify no extra tools are registered."""
        assert len(tool_functions) == 3


class TestSkillsListTool:
    """Tests for the skills_list tool function."""

    @pytest.mark.asyncio
    async def test_delegates_to_registry(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify tool delegates to registry.list_skills."""
        expected = [
            {"name": "skill1", "description": "desc1", "args": [], "tags": []}
        ]
        mock_registry.list_skills.return_value = expected

        result = await tool_functions["skills_list"]()

        mock_registry.list_skills.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify empty list returned when no skills registered."""
        mock_registry.list_skills.return_value = []

        result = await tool_functions["skills_list"]()

        assert result == []


class TestSkillsGetInfoTool:
    """Tests for the skills_get_info tool function."""

    @pytest.mark.asyncio
    async def test_returns_skill_details(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify tool returns full skill details when found."""
        skill = _make_skill(
            name="my-skill",
            description="Does something",
            command="do-it",
            args=[
                SkillArgument(
                    name="target",
                    description="The target",
                    required=True,
                    default=None,
                )
            ],
            tags=["util"],
            timeout=60,
            documentation="Full docs here",
        )
        mock_registry.get_skill.return_value = skill

        result = await tool_functions["skills_get_info"](name="my-skill")

        mock_registry.get_skill.assert_called_once_with("my-skill")
        assert result["name"] == "my-skill"
        assert result["description"] == "Does something"
        assert result["timeout"] == 60
        assert result["documentation"] == "Full docs here"
        assert result["tags"] == ["util"]
        assert result["max_output_bytes"] is None
        assert len(result["args"]) == 1
        assert result["args"][0]["name"] == "target"
        assert result["args"][0]["required"] is True

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify SkillNotFoundError is raised when skill not found."""
        mock_registry.get_skill.return_value = None

        with pytest.raises(SkillNotFoundError, match="nonexistent"):
            await tool_functions["skills_get_info"](name="nonexistent")

    @pytest.mark.asyncio
    async def test_returns_max_output_bytes_when_set(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify max_output_bytes is returned when set on skill."""
        skill = _make_skill()
        skill.max_output_bytes = 262144
        mock_registry.get_skill.return_value = skill

        result = await tool_functions["skills_get_info"](name="test-skill")

        assert result["max_output_bytes"] == 262144

    @pytest.mark.asyncio
    async def test_returns_empty_args_and_tags(
        self, tool_functions: dict[str, Any], mock_registry: MagicMock
    ) -> None:
        """Verify skill with no args/tags returns empty lists."""
        skill = _make_skill(args=[], tags=[])
        mock_registry.get_skill.return_value = skill

        result = await tool_functions["skills_get_info"](name="test-skill")

        assert result["args"] == []
        assert result["tags"] == []


class TestSkillsExecuteTool:
    """Tests for the skills_execute tool function."""

    @pytest.mark.asyncio
    async def test_executes_skill_successfully(
        self,
        tool_functions: dict[str, Any],
        mock_registry: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Verify successful execution returns correct result dict."""
        skill = _make_skill()
        mock_registry.get_skill.return_value = skill
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="output here",
            stderr="",
            timed_out=False,
        )

        result = await tool_functions["skills_execute"](
            name="test-skill", args={"key": "value"}
        )

        mock_registry.get_skill.assert_called_once_with("test-skill")
        mock_executor.execute.assert_called_once_with(skill, {"key": "value"})
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["stdout"] == "output here"
        assert result["stderr"] == ""
        assert result["timed_out"] is False

    @pytest.mark.asyncio
    async def test_raises_when_skill_not_found(
        self,
        tool_functions: dict[str, Any],
        mock_registry: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Verify SkillNotFoundError raised when skill does not exist."""
        mock_registry.get_skill.return_value = None

        with pytest.raises(SkillNotFoundError, match="missing"):
            await tool_functions["skills_execute"](name="missing")

        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_on_failed_execution(
        self,
        tool_functions: dict[str, Any],
        mock_registry: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Verify SkillExecutionError raised when execution fails."""
        skill = _make_skill()
        mock_registry.get_skill.return_value = skill
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="command not found",
            timed_out=False,
        )

        with pytest.raises(SkillExecutionError, match="command not found"):
            await tool_functions["skills_execute"](name="test-skill")

    @pytest.mark.asyncio
    async def test_raises_on_timeout(
        self,
        tool_functions: dict[str, Any],
        mock_registry: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Verify SkillTimeoutError raised when execution times out."""
        skill = _make_skill()
        mock_registry.get_skill.return_value = skill
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Command timed out after 30 seconds",
            timed_out=True,
        )

        with pytest.raises(SkillTimeoutError, match="timed out"):
            await tool_functions["skills_execute"](name="test-skill")

    @pytest.mark.asyncio
    async def test_passes_none_args_when_omitted(
        self,
        tool_functions: dict[str, Any],
        mock_registry: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Verify None is passed as args when not provided."""
        skill = _make_skill()
        mock_registry.get_skill.return_value = skill
        mock_executor.execute.return_value = ExecutionResult(
            success=True, exit_code=0, stdout="", stderr=""
        )

        await tool_functions["skills_execute"](name="test-skill")

        mock_executor.execute.assert_called_once_with(skill, None)
