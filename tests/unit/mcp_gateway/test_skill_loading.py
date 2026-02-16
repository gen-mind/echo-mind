"""Integration tests for loading real SKILL.md files from config/mcp-gateway/skills/."""

import os

import pytest

from mcp_gateway.skills.registry import SkillRegistry

# Path to real skills directory
SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "mcp-gateway", "skills"
)

# All 42 portable skills
ALL_SKILL_NAMES = {
    # Initial 5
    "weather", "github", "summarize", "coding-agent", "file-edit",
    # Additional Direct
    "trello", "notion", "slack", "discord", "openai-image-gen",
    # Direct batch 1
    "tmux", "nano-pdf", "video-frames", "gemini", "openai-whisper-api", "1password",
    # Direct batch 2
    "bird", "blogwatcher", "gifgrep", "goplaces", "sag", "songsee",
    # Direct batch 3
    "mcporter", "nano-banana-pro", "oracle", "obsidian", "skill-creator",
    # Adapt
    "camsnap", "gog", "himalaya", "local-places", "openai-whisper",
    "sherpa-onnx-tts", "wacli", "lobster",
    # Replace + EchoMind-native
    "skill-registry", "session-logs", "model-usage",
    "echomind-search", "echomind-documents", "echomind-connectors", "echomind-memory",
}


class TestRealSkillLoading:
    """Tests that validate the actual SKILL.md files parse correctly."""

    def test_loads_all_skills(self) -> None:
        """Registry loads all 42 portable skills."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        count = registry.load()
        assert count == 42

    def test_weather_skill_parsed(self) -> None:
        """Weather skill has correct metadata."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skill = registry.get_skill("weather")
        assert skill is not None
        assert skill.description
        assert "curl" in skill.command
        assert "wttr.in" in skill.command
        assert skill.timeout == 10
        assert skill.max_output_bytes is None
        # Has location arg (optional with empty default)
        location_args = [a for a in skill.args if a.name == "location"]
        assert len(location_args) == 1
        assert location_args[0].required is False
        assert location_args[0].default == ""
        # Has format arg (optional with default "3")
        format_args = [a for a in skill.args if a.name == "format"]
        assert len(format_args) == 1
        assert format_args[0].required is False
        assert format_args[0].default == "3"

    def test_github_skill_parsed(self) -> None:
        """GitHub skill has correct metadata."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skill = registry.get_skill("github")
        assert skill is not None
        assert "gh" in skill.command
        assert skill.timeout == 60
        assert skill.max_output_bytes == 262144
        # Has required command arg
        cmd_args = [a for a in skill.args if a.name == "command"]
        assert len(cmd_args) == 1
        assert cmd_args[0].required is True

    def test_coding_agent_extended_limits(self) -> None:
        """Coding-agent skill has extended timeout and output limits."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skill = registry.get_skill("coding-agent")
        assert skill is not None
        assert skill.timeout == 120
        assert skill.max_output_bytes == 262144  # 256KB

    def test_summarize_skill_has_output_limit(self) -> None:
        """Summarize skill has custom output limit."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skill = registry.get_skill("summarize")
        assert skill is not None
        assert skill.max_output_bytes == 131072  # 128KB
        assert skill.timeout == 45
        # Has required url arg and optional max_chars arg
        url_args = [a for a in skill.args if a.name == "url"]
        assert len(url_args) == 1
        assert url_args[0].required is True
        max_chars_args = [a for a in skill.args if a.name == "max_chars"]
        assert len(max_chars_args) == 1
        assert max_chars_args[0].required is False
        assert max_chars_args[0].default == "100000"

    def test_file_edit_skill_parsed(self) -> None:
        """File-edit skill has correct metadata."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skill = registry.get_skill("file-edit")
        assert skill is not None
        assert skill.timeout == 30
        assert skill.max_output_bytes is None
        # Has required command arg
        cmd_args = [a for a in skill.args if a.name == "command"]
        assert len(cmd_args) == 1
        assert cmd_args[0].required is True

    def test_all_skills_have_documentation(self) -> None:
        """All 42 skills have non-empty documentation."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        for name in ALL_SKILL_NAMES:
            skill = registry.get_skill(name)
            assert skill is not None, f"Skill {name} not found"
            assert skill.documentation, f"Skill {name} has no documentation"
            assert len(skill.documentation) > 50, f"Skill {name} documentation too short"

    def test_all_skills_have_tags(self) -> None:
        """All 42 skills have at least one tag."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        for name in ALL_SKILL_NAMES:
            skill = registry.get_skill(name)
            assert skill is not None, f"Skill {name} not found"
            assert len(skill.tags) > 0, f"Skill {name} has no tags"

    def test_all_skills_have_valid_timeout(self) -> None:
        """All skills have a positive timeout."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        for name in ALL_SKILL_NAMES:
            skill = registry.get_skill(name)
            assert skill is not None, f"Skill {name} not found"
            assert skill.timeout > 0, f"Skill {name} has invalid timeout: {skill.timeout}"

    def test_all_skills_have_command(self) -> None:
        """All skills have a non-empty command."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        for name in ALL_SKILL_NAMES:
            skill = registry.get_skill(name)
            assert skill is not None, f"Skill {name} not found"
            assert skill.command.strip(), f"Skill {name} has empty command"

    def test_list_skills_returns_all(self) -> None:
        """list_skills() returns summaries for all 42 skills."""
        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        registry.load()
        skills = registry.list_skills()
        names = {s["name"] for s in skills}
        assert names == ALL_SKILL_NAMES
