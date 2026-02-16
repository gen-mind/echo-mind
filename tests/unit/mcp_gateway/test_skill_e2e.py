"""End-to-end integration tests for skill execution pipeline."""

import os

import pytest

from mcp_gateway.skills.executor import SkillExecutor
from mcp_gateway.skills.registry import SkillRegistry

SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "mcp-gateway", "skills"
)


class TestSkillE2E:
    """E2E tests executing real commands through the skill pipeline."""

    @pytest.mark.asyncio
    async def test_execute_echo_skill(self, tmp_path) -> None:
        """Execute a simple echo skill and verify stdout."""
        skill_dir = tmp_path / "echo-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: echo-test\ndescription: Echo test\ncommand: echo ${message}\n"
            "args:\n  - name: message\n    description: Message to echo\n    required: true\n---\nTest skill."
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("echo-test")
        executor = SkillExecutor()
        result = await executor.execute(skill, {"message": "hello world"})
        assert result.success is True
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_pipe_command(self, tmp_path) -> None:
        """Execute skill with pipe and verify output."""
        skill_dir = tmp_path / "pipe-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: pipe-test\ndescription: Pipe test\ncommand: echo "one two three" | wc -w\n---\nPipe test.'
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("pipe-test")
        executor = SkillExecutor()
        result = await executor.execute(skill)
        assert result.success is True
        assert "3" in result.stdout.strip()

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tmp_path) -> None:
        """Skill times out correctly."""
        skill_dir = tmp_path / "timeout-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: timeout-test\ndescription: Timeout test\ncommand: sleep 10\ntimeout: 1\n---\nTimeout test."
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("timeout-test")
        executor = SkillExecutor()
        result = await executor.execute(skill)
        assert result.success is False
        assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_execute_failure(self, tmp_path) -> None:
        """Skill with non-zero exit code."""
        skill_dir = tmp_path / "fail-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: fail-test\ndescription: Fail test\ncommand: exit 42\n---\nFail test."
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("fail-test")
        executor = SkillExecutor()
        result = await executor.execute(skill)
        assert result.success is False
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_execute_output_truncation(self, tmp_path) -> None:
        """Output is truncated when exceeding max_output_bytes."""
        skill_dir = tmp_path / "truncate-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: truncate-test\ndescription: Truncation test\n"
            "command: python3 -c \"print('x' * 2000)\"\nmax_output_bytes: 1024\n---\nTest."
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("truncate-test")
        executor = SkillExecutor()
        result = await executor.execute(skill)
        assert result.success is True
        assert "... [output truncated]" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_missing_required_arg(self, tmp_path) -> None:
        """Missing required arg returns error."""
        skill_dir = tmp_path / "required-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: required-test\ndescription: Required arg test\ncommand: echo ${name}\n"
            "args:\n  - name: name\n    description: Name\n    required: true\n---\nTest."
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("required-test")
        executor = SkillExecutor()
        result = await executor.execute(skill, {})
        assert result.success is False
        assert "Missing required argument" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_default_arg(self, tmp_path) -> None:
        """Default arg value is used when arg not provided."""
        skill_dir = tmp_path / "default-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-test\ndescription: Default arg test\ncommand: echo ${greeting}\n"
            'args:\n  - name: greeting\n    description: Greeting\n    default: "hello"\n---\nTest.'
        )
        registry = SkillRegistry(skills_dir=str(tmp_path))
        registry.load()
        skill = registry.get_skill("default-test")
        executor = SkillExecutor()
        result = await executor.execute(skill, {})
        assert result.success is True
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_real_skills_load_successfully(self) -> None:
        """All real skills from config/ load without errors."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        count = registry.load()
        assert count == 42
        # Verify each one has a valid name and command
        for skill_summary in registry.list_skills():
            skill = registry.get_skill(skill_summary["name"])
            assert skill is not None
            assert skill.command
            assert skill.description
