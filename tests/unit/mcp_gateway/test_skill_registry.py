"""Tests for skill registry."""

import pytest

from mcp_gateway.skills.registry import SkillArgument, SkillDefinition, SkillRegistry


FULL_SKILL_MD = """\
---
name: test-skill
description: A test skill
command: echo hello
args:
  - name: input
    description: Input text
    required: true
  - name: format
    description: Output format
    required: false
    default: json
tags:
  - test
  - example
timeout: 60
---
# Test Skill

This is the documentation body.
"""

MINIMAL_SKILL_MD = """\
---
name: minimal
description: Minimal skill
command: echo minimal
---
"""


class TestSkillArgument:
    """Tests for SkillArgument dataclass."""

    def test_defaults(self) -> None:
        """Test default values for optional fields."""
        arg = SkillArgument(name="foo", description="bar")
        assert arg.required is False
        assert arg.default is None

    def test_all_fields(self) -> None:
        """Test creating with all fields."""
        arg = SkillArgument(
            name="input",
            description="The input",
            required=True,
            default="hello",
        )
        assert arg.name == "input"
        assert arg.description == "The input"
        assert arg.required is True
        assert arg.default == "hello"


class TestSkillDefinition:
    """Tests for SkillDefinition dataclass."""

    def test_defaults(self) -> None:
        """Test default values for optional fields."""
        skill = SkillDefinition(name="s", description="d", command="c")
        assert skill.args == []
        assert skill.tags == []
        assert skill.timeout == 30
        assert skill.documentation == ""
        assert skill.source_path == ""


class TestSkillRegistryLoad:
    """Tests for SkillRegistry.load()."""

    def test_load_valid_skills(self, tmp_path: object) -> None:
        """Test loading skills from a directory with valid SKILL.md files."""
        # Create two skill directories
        skill_a = tmp_path / "skill-a"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(FULL_SKILL_MD)

        skill_b = tmp_path / "skill-b"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text(MINIMAL_SKILL_MD)

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()

        assert count == 2
        assert registry.skill_count == 2

    def test_load_parses_full_frontmatter(self, tmp_path: object) -> None:
        """Test that full frontmatter fields are correctly parsed."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(FULL_SKILL_MD)

        registry = SkillRegistry(str(tmp_path))
        registry.load()

        skill = registry.get_skill("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.command == "echo hello"
        assert skill.timeout == 60
        assert skill.tags == ["test", "example"]
        assert skill.documentation == "# Test Skill\n\nThis is the documentation body."
        assert str(skill_dir / "SKILL.md") in skill.source_path

        # Check args
        assert len(skill.args) == 2
        assert skill.args[0].name == "input"
        assert skill.args[0].required is True
        assert skill.args[0].default is None
        assert skill.args[1].name == "format"
        assert skill.args[1].required is False
        assert skill.args[1].default == "json"

    def test_load_parses_minimal_frontmatter(self, tmp_path: object) -> None:
        """Test parsing SKILL.md with minimal frontmatter (no args, no tags)."""
        skill_dir = tmp_path / "min"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD)

        registry = SkillRegistry(str(tmp_path))
        registry.load()

        skill = registry.get_skill("minimal")
        assert skill is not None
        assert skill.args == []
        assert skill.tags == []
        assert skill.timeout == 30
        assert skill.documentation == ""

    def test_load_nonexistent_directory(self, tmp_path: object) -> None:
        """Test loading from a non-existent directory returns 0."""
        registry = SkillRegistry(str(tmp_path / "nonexistent"))
        count = registry.load()
        assert count == 0
        assert registry.skill_count == 0

    def test_load_skips_dirs_without_skill_md(self, tmp_path: object) -> None:
        """Test that directories without SKILL.md are skipped."""
        (tmp_path / "no-skill").mkdir()
        (tmp_path / "no-skill" / "README.md").write_text("not a skill")

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0

    def test_load_skips_files_in_root(self, tmp_path: object) -> None:
        """Test that files (not directories) in the skills dir are skipped."""
        (tmp_path / "somefile.txt").write_text("not a dir")

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0

    def test_load_skips_invalid_and_loads_valid(self, tmp_path: object) -> None:
        """Test that invalid SKILL.md files are skipped while valid ones load."""
        good = tmp_path / "good"
        good.mkdir()
        (good / "SKILL.md").write_text(MINIMAL_SKILL_MD)

        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "SKILL.md").write_text("no frontmatter here")

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 1
        assert registry.get_skill("minimal") is not None

    def test_load_clears_previous_skills(self, tmp_path: object) -> None:
        """Test that load() clears previously loaded skills."""
        skill_dir = tmp_path / "s1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD)

        registry = SkillRegistry(str(tmp_path))
        registry.load()
        assert registry.skill_count == 1

        # Remove the skill and reload
        (skill_dir / "SKILL.md").unlink()
        registry.load()
        assert registry.skill_count == 0


class TestSkillRegistryParseErrors:
    """Tests for SKILL.md parsing error cases."""

    def test_missing_frontmatter_markers(self, tmp_path: object) -> None:
        """Test that missing --- markers raise ValueError."""
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("no frontmatter")

        registry = SkillRegistry(str(tmp_path))
        # load() catches exceptions, so count is 0
        count = registry.load()
        assert count == 0

    def test_missing_required_field_name(self, tmp_path: object) -> None:
        """Test that missing 'name' field causes parse failure."""
        content = """\
---
description: No name
command: echo test
---
"""
        skill_dir = tmp_path / "noname"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(content)

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0

    def test_missing_required_field_description(self, tmp_path: object) -> None:
        """Test that missing 'description' field causes parse failure."""
        content = """\
---
name: nodesc
command: echo test
---
"""
        skill_dir = tmp_path / "nodesc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(content)

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0

    def test_missing_required_field_command(self, tmp_path: object) -> None:
        """Test that missing 'command' field causes parse failure."""
        content = """\
---
name: nocmd
description: No command
---
"""
        skill_dir = tmp_path / "nocmd"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(content)

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0

    def test_incomplete_frontmatter_single_marker(self, tmp_path: object) -> None:
        """Test that a single --- marker (no closing) raises ValueError."""
        content = """\
---
name: incomplete
"""
        skill_dir = tmp_path / "inc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(content)

        registry = SkillRegistry(str(tmp_path))
        count = registry.load()
        assert count == 0


class TestSkillRegistryLookup:
    """Tests for get_skill() and list_skills()."""

    def test_get_skill_returns_none_for_unknown(self) -> None:
        """Test that get_skill returns None for non-existent skill."""
        registry = SkillRegistry("/nonexistent")
        assert registry.get_skill("unknown") is None

    def test_list_skills_empty(self) -> None:
        """Test list_skills returns empty list when no skills loaded."""
        registry = SkillRegistry("/nonexistent")
        assert registry.list_skills() == []

    def test_list_skills_format(self, tmp_path: object) -> None:
        """Test that list_skills returns correct dict format."""
        skill_dir = tmp_path / "s1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(FULL_SKILL_MD)

        registry = SkillRegistry(str(tmp_path))
        registry.load()

        skills = registry.list_skills()
        assert len(skills) == 1
        s = skills[0]
        assert s["name"] == "test-skill"
        assert s["description"] == "A test skill"
        assert s["tags"] == ["test", "example"]
        assert len(s["args"]) == 2
        assert s["args"][0]["name"] == "input"
        assert s["args"][0]["required"] is True
        assert s["args"][1]["default"] == "json"

    def test_skill_count_property(self, tmp_path: object) -> None:
        """Test skill_count property reflects loaded skills."""
        registry = SkillRegistry(str(tmp_path))
        assert registry.skill_count == 0

        skill_dir = tmp_path / "s1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(MINIMAL_SKILL_MD)
        registry.load()
        assert registry.skill_count == 1
