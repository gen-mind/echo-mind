"""
Skill registry for discovering and parsing SKILL.md files.

Scans a directory for SKILL.md files, parses YAML frontmatter,
and provides a registry of available skills.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("echomind-mcp-gateway")


@dataclass
class SkillArgument:
    """Definition of a skill argument."""

    name: str
    description: str
    required: bool = False
    default: str | None = None


@dataclass
class SkillDefinition:
    """Parsed skill definition from a SKILL.md file."""

    name: str
    description: str
    command: str
    args: list[SkillArgument] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    timeout: int = 30
    documentation: str = ""
    source_path: str = ""


class SkillRegistry:
    """
    Registry that discovers and manages skill definitions.

    Scans a directory for SKILL.md files, parses their YAML
    frontmatter, and maintains a lookup of available skills.
    """

    SKILL_FILENAME = "SKILL.md"

    def __init__(self, skills_dir: str) -> None:
        """
        Initialize skill registry.

        Args:
            skills_dir: Path to directory containing skill subdirectories.
        """
        self._skills_dir = skills_dir
        self._skills: dict[str, SkillDefinition] = {}

    def load(self) -> int:
        """
        Scan skills directory and load all SKILL.md files.

        Returns:
            Number of skills loaded.

        Raises:
            FileNotFoundError: If skills directory does not exist.
        """
        skills_path = Path(self._skills_dir)
        if not skills_path.exists():
            logger.warning(f"⚠️ Skills directory not found: {self._skills_dir}")
            return 0

        self._skills.clear()
        count = 0

        for item in sorted(skills_path.iterdir()):
            if not item.is_dir():
                continue

            skill_file = item / self.SKILL_FILENAME
            if not skill_file.exists():
                continue

            try:
                skill = self._parse_skill_file(skill_file)
                self._skills[skill.name] = skill
                count += 1
                logger.info(f"📦 Loaded skill: {skill.name}")
            except Exception as e:
                logger.error(f"❌ Failed to parse {skill_file}: {e}")

        logger.info(f"✅ Loaded {count} skills from {self._skills_dir}")
        return count

    def _parse_skill_file(self, path: Path) -> SkillDefinition:
        """
        Parse a SKILL.md file into a SkillDefinition.

        Args:
            path: Path to the SKILL.md file.

        Returns:
            Parsed SkillDefinition.

        Raises:
            ValueError: If YAML frontmatter is missing or invalid.
        """
        content = path.read_text(encoding="utf-8")

        # Parse YAML frontmatter (between --- markers)
        if not content.startswith("---"):
            raise ValueError(f"Missing YAML frontmatter in {path}")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid YAML frontmatter in {path}")

        frontmatter = yaml.safe_load(parts[1])
        if not isinstance(frontmatter, dict):
            raise ValueError(f"YAML frontmatter must be a mapping in {path}")

        documentation = parts[2].strip()

        # Validate required fields
        for required in ("name", "description", "command"):
            if required not in frontmatter:
                raise ValueError(f"Missing required field '{required}' in {path}")

        # Parse arguments
        args = []
        for arg_data in frontmatter.get("args", []):
            args.append(SkillArgument(
                name=arg_data["name"],
                description=arg_data.get("description", ""),
                required=arg_data.get("required", False),
                default=arg_data.get("default"),
            ))

        return SkillDefinition(
            name=frontmatter["name"],
            description=frontmatter["description"],
            command=frontmatter["command"],
            args=args,
            tags=frontmatter.get("tags", []),
            timeout=frontmatter.get("timeout", 30),
            documentation=documentation,
            source_path=str(path),
        )

    def get_skill(self, name: str) -> SkillDefinition | None:
        """
        Get a skill definition by name.

        Args:
            name: Skill name.

        Returns:
            SkillDefinition if found, None otherwise.
        """
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        """
        List all registered skills.

        Returns:
            List of skill summaries with name, description, args, and tags.
        """
        return [
            {
                "name": s.name,
                "description": s.description,
                "args": [
                    {
                        "name": a.name,
                        "description": a.description,
                        "required": a.required,
                        "default": a.default,
                    }
                    for a in s.args
                ],
                "tags": s.tags,
            }
            for s in self._skills.values()
        ]

    @property
    def skill_count(self) -> int:
        """Number of registered skills."""
        return len(self._skills)
