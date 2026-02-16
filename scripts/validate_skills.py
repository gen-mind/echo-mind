#!/usr/bin/env python3
"""
Validate SKILL.md files for errors and inconsistencies.

Scans a directory for SKILL.md files, parses YAML frontmatter,
and reports errors, warnings, and validation status.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ValidationResult:
    """Result of validating a single SKILL.md file."""

    name: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


REQUIRED_FIELDS = ("name", "description", "command")


def validate_skill_file(path: Path) -> ValidationResult:
    """
    Validate a SKILL.md file for correctness.

    Args:
        path: Path to the SKILL.md file.

    Returns:
        ValidationResult with errors and warnings.
    """
    dir_name = path.parent.name
    result = ValidationResult(name=dir_name, valid=True)

    # Read file
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        result.valid = False
        result.errors.append(f"Cannot read file: {e}")
        return result

    # Check YAML frontmatter exists
    if not content.startswith("---"):
        result.valid = False
        result.errors.append("Missing YAML frontmatter (file must start with ---)")
        return result

    parts = content.split("---", 2)
    if len(parts) < 3:
        result.valid = False
        result.errors.append("Invalid YAML frontmatter (missing closing ---)")
        return result

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        result.valid = False
        result.errors.append(f"YAML parse error: {e}")
        return result

    if not isinstance(frontmatter, dict):
        result.valid = False
        result.errors.append("YAML frontmatter must be a mapping")
        return result

    # Required fields
    for req in REQUIRED_FIELDS:
        if req not in frontmatter:
            result.valid = False
            result.errors.append(f"Missing required field '{req}'")

    # If required fields missing, skip further validation
    if not result.valid:
        return result

    skill_name = frontmatter["name"]
    result.name = skill_name

    # Args validation
    args_data = frontmatter.get("args", [])
    defined_arg_names: set[str] = set()
    if isinstance(args_data, list):
        for i, arg in enumerate(args_data):
            if not isinstance(arg, dict):
                result.valid = False
                result.errors.append(f"Arg at index {i} is not a mapping")
                continue
            if "name" not in arg:
                result.valid = False
                result.errors.append(f"Arg at index {i} missing required 'name' field")
            else:
                defined_arg_names.add(arg["name"])

    # Timeout validation
    timeout = frontmatter.get("timeout")
    if timeout is not None:
        if not isinstance(timeout, int) or timeout <= 0:
            result.valid = False
            result.errors.append(
                f"'timeout' must be a positive integer, got {timeout!r}"
            )

    # max_output_bytes validation
    max_output = frontmatter.get("max_output_bytes")
    if max_output is not None:
        if not isinstance(max_output, int) or max_output <= 0:
            result.valid = False
            result.errors.append(
                f"'max_output_bytes' must be a positive integer, got {max_output!r}"
            )

    # Placeholder/arg mismatch
    command = frontmatter["command"]
    placeholders = set(re.findall(r"\$\{(\w+)}", command))
    unused_args = defined_arg_names - placeholders
    undefined_placeholders = placeholders - defined_arg_names

    for arg_name in sorted(unused_args):
        result.warnings.append(
            f"Unused arg '{arg_name}' not in command template"
        )
    for ph in sorted(undefined_placeholders):
        result.warnings.append(
            f"Placeholder '${{{ph}}}' in command has no matching arg definition"
        )

    # Name/directory mismatch
    if skill_name != dir_name:
        result.warnings.append(
            f"Skill name '{skill_name}' does not match directory name '{dir_name}'"
        )

    # Documentation section
    documentation = parts[2].strip()
    if not documentation:
        result.warnings.append("Documentation section is empty")

    return result


def validate_skills_directory(skills_dir: Path) -> list[ValidationResult]:
    """
    Validate all SKILL.md files in a directory.

    Args:
        skills_dir: Path to directory containing skill subdirectories.

    Returns:
        List of ValidationResult for each SKILL.md found.
    """
    results: list[ValidationResult] = []

    if not skills_dir.exists():
        return results

    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue
        skill_file = item / "SKILL.md"
        if not skill_file.exists():
            continue
        results.append(validate_skill_file(skill_file))

    return results


def main() -> int:
    """
    Run skill validation from the command line.

    Returns:
        Exit code: 0 if no errors, 1 if any errors found.
    """
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files for errors and inconsistencies."
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Path to skills directory (default: config/mcp-gateway/skills/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation output",
    )
    args = parser.parse_args()

    if args.dir:
        skills_dir = Path(args.dir)
    else:
        # Find relative to script location
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parent
        skills_dir = project_root / "config" / "mcp-gateway" / "skills"

    print(f"Validating skills in {skills_dir}...")

    if not skills_dir.exists():
        print(f"❌ Skills directory not found: {skills_dir}")
        return 1

    results = validate_skills_directory(skills_dir)

    if not results:
        print("  No SKILL.md files found.")
        return 0

    total_valid = 0
    total_warnings = 0
    total_errors = 0

    for r in results:
        if r.errors:
            total_errors += 1
            print(f"  ❌ {r.name} — {'; '.join(r.errors)}")
            if args.verbose:
                for err in r.errors:
                    print(f"       error: {err}")
        elif r.warnings:
            total_warnings += 1
            total_valid += 1
            print(f"  ⚠️  {r.name} — {'; '.join(r.warnings)}")
            if args.verbose:
                for warn in r.warnings:
                    print(f"       warning: {warn}")
        else:
            total_valid += 1
            print(f"  ✅ {r.name} — valid")

    print()
    print(
        f"Summary: {len(results)} skills validated, "
        f"{total_valid} valid, {total_warnings} warnings, {total_errors} errors"
    )

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
