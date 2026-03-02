"""Tests for the skill validation script."""

from pathlib import Path

import pytest

from scripts.validate_skills import ValidationResult, validate_skill_file, validate_skills_directory


def _write_skill(tmp_path: Path, name: str, content: str) -> Path:
    """Helper to create a SKILL.md file in a named subdirectory."""
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


VALID_SKILL = """\
---
name: weather
description: "Get weather forecasts"
command: "curl -s wttr.in/${location}"
args:
  - name: location
    description: "City name"
    required: false
    default: ""
tags: [weather, utility]
timeout: 10
---

# Weather Skill

Get weather forecasts from wttr.in.
"""

VALID_SKILL_ALL_OPTIONAL = """\
---
name: summarize
description: "Fetch and summarize URLs"
command: "curl -sL ${url} | head -c ${max_chars}"
args:
  - name: url
    description: "URL to fetch"
    required: true
  - name: max_chars
    description: "Max characters"
    required: false
    default: "100000"
tags: [web, utility]
timeout: 45
max_output_bytes: 131072
---

# Summarize Skill

Fetches content from URLs for summarization.
"""


class TestValidateSkillFile:
    """Tests for validate_skill_file function."""

    def test_valid_skill_passes(self, tmp_path: Path) -> None:
        """Valid SKILL.md should pass with no errors or warnings."""
        path = _write_skill(tmp_path, "weather", VALID_SKILL)
        result = validate_skill_file(path)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.name == "weather"

    def test_missing_name_fails(self, tmp_path: Path) -> None:
        """Missing 'name' field should produce an error."""
        content = """\
---
description: "Some skill"
command: "echo hello"
---

# Docs
"""
        path = _write_skill(tmp_path, "test-skill", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_missing_description_fails(self, tmp_path: Path) -> None:
        """Missing 'description' field should produce an error."""
        content = """\
---
name: test
command: "echo hello"
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("description" in e for e in result.errors)

    def test_missing_command_fails(self, tmp_path: Path) -> None:
        """Missing 'command' field should produce an error."""
        content = """\
---
name: test
description: "A test skill"
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("command" in e for e in result.errors)

    def test_invalid_yaml_fails(self, tmp_path: Path) -> None:
        """Invalid YAML should produce an error."""
        content = """\
---
name: test
description: [invalid yaml
  : broken
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("YAML" in e or "parse" in e.lower() for e in result.errors)

    def test_missing_frontmatter_fails(self, tmp_path: Path) -> None:
        """File without YAML frontmatter should fail."""
        content = "# Just a markdown file\n\nNo frontmatter here."
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("frontmatter" in e.lower() for e in result.errors)

    def test_placeholder_arg_mismatch_warns(self, tmp_path: Path) -> None:
        """Unused arg not in command template should produce a warning."""
        content = """\
---
name: test
description: "A test skill"
command: "echo ${msg}"
args:
  - name: msg
    description: "Message"
  - name: unused_arg
    description: "Not used in command"
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is True
        assert any("unused_arg" in w for w in result.warnings)

    def test_undefined_placeholder_warns(self, tmp_path: Path) -> None:
        """Placeholder in command with no matching arg should warn."""
        content = """\
---
name: test
description: "A test skill"
command: "echo ${undefined_var}"
args: []
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is True
        assert any("undefined_var" in w for w in result.warnings)

    def test_name_directory_mismatch_warns(self, tmp_path: Path) -> None:
        """Skill name not matching directory name should produce a warning."""
        content = """\
---
name: different-name
description: "A test skill"
command: "echo hello"
---

# Docs
"""
        path = _write_skill(tmp_path, "my-dir", content)
        result = validate_skill_file(path)
        assert result.valid is True
        assert any("does not match directory" in w for w in result.warnings)

    def test_empty_documentation_warns(self, tmp_path: Path) -> None:
        """Empty documentation section should produce a warning."""
        content = """\
---
name: test
description: "A test skill"
command: "echo hello"
---
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is True
        assert any("Documentation" in w or "empty" in w.lower() for w in result.warnings)

    def test_valid_skill_with_all_optional_fields(self, tmp_path: Path) -> None:
        """Skill with all optional fields should pass validation."""
        path = _write_skill(tmp_path, "summarize", VALID_SKILL_ALL_OPTIONAL)
        result = validate_skill_file(path)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_timeout_fails(self, tmp_path: Path) -> None:
        """Non-positive timeout should produce an error."""
        content = """\
---
name: test
description: "A test skill"
command: "echo hello"
timeout: -5
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("timeout" in e for e in result.errors)

    def test_invalid_max_output_bytes_fails(self, tmp_path: Path) -> None:
        """Non-positive max_output_bytes should produce an error."""
        content = """\
---
name: test
description: "A test skill"
command: "echo hello"
max_output_bytes: 0
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("max_output_bytes" in e for e in result.errors)

    def test_arg_missing_name_fails(self, tmp_path: Path) -> None:
        """Arg without a 'name' field should produce an error."""
        content = """\
---
name: test
description: "A test skill"
command: "echo hello"
args:
  - description: "No name field"
---

# Docs
"""
        path = _write_skill(tmp_path, "test", content)
        result = validate_skill_file(path)
        assert result.valid is False
        assert any("name" in e and "Arg" in e for e in result.errors)


class TestValidateSkillsDirectory:
    """Tests for validate_skills_directory function."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory should return no results."""
        results = validate_skills_directory(tmp_path)
        assert results == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Nonexistent directory should return no results."""
        results = validate_skills_directory(tmp_path / "nonexistent")
        assert results == []

    def test_multiple_skills(self, tmp_path: Path) -> None:
        """Directory with multiple skills should validate all."""
        _write_skill(tmp_path, "weather", VALID_SKILL)
        _write_skill(tmp_path, "summarize", VALID_SKILL_ALL_OPTIONAL)
        results = validate_skills_directory(tmp_path)
        assert len(results) == 2
        assert all(r.valid for r in results)


class TestRealSkills:
    """Tests against actual skill files in the repository."""

    def test_real_skills_all_valid(self) -> None:
        """All real SKILL.md files in config/mcp-gateway/skills/ should be valid."""
        project_root = Path(__file__).resolve().parents[3]
        skills_dir = project_root / "config" / "mcp-gateway" / "skills"

        if not skills_dir.exists():
            pytest.skip("Skills directory not found")

        results = validate_skills_directory(skills_dir)
        if not results:
            pytest.skip("No SKILL.md files found")

        errors = [r for r in results if not r.valid]
        if errors:
            error_details = "\n".join(
                f"  {r.name}: {'; '.join(r.errors)}" for r in errors
            )
            pytest.fail(f"Skills with errors:\n{error_details}")
