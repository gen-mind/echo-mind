---
name: skill-creator
description: "Guide for creating new SKILL.md files for the EchoMind skill system"
command: "echo \"Skill Creator is a documentation-only skill. Read the documentation for instructions.\""
tags: [meta, documentation, skills, development]
timeout: 5
---

# Skill Creator Guide

Comprehensive guide for creating new SKILL.md files for the EchoMind skill system. Each skill is a self-contained definition that tells the MCP gateway how to execute a command and what arguments it accepts.

## Directory Structure

```
config/mcp-gateway/skills/
  {skill-name}/
    SKILL.md
```

Each skill lives in its own directory under `config/mcp-gateway/skills/`. The directory name should match the skill `name` field.

## SKILL.md Format

Every SKILL.md file has two parts:

1. **YAML frontmatter** (between `---` delimiters) — machine-readable metadata
2. **Markdown body** — human-readable documentation

### Minimal Example

```markdown
---
name: my-skill
description: "What this skill does in one sentence"
command: "${command}"
args:
  - name: command
    description: "The command to execute"
    required: true
tags: [category1, category2]
timeout: 30
---

# My Skill

Documentation and usage examples go here.
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique skill identifier (lowercase, hyphens allowed) |
| `description` | string | One-line description shown in skill listings |
| `command` | string | Command template to execute (supports `${placeholder}` interpolation) |

## Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `args` | list | `[]` | Argument definitions (see below) |
| `tags` | list | `[]` | Categories for discovery and filtering |
| `timeout` | integer | `30` | Max execution time in seconds |
| `max_output_bytes` | integer | `65536` | Max output size before truncation |

## Argument Definitions

Each argument in the `args` list supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Argument name (used in `${name}` interpolation) |
| `description` | string | Yes | What this argument is for |
| `required` | boolean | No | Whether the argument must be provided (default: `false`) |
| `default` | string | No | Default value if not provided |

### Example with Multiple Args

```yaml
args:
  - name: command
    description: "The API command to run"
    required: true
  - name: format
    description: "Output format"
    required: false
    default: "json"
  - name: verbose
    description: "Enable verbose output"
    required: false
    default: "false"
```

## Command Templates

The `command` field supports `${placeholder}` interpolation. Placeholders are replaced with argument values at execution time.

```yaml
# Single argument — the command IS the argument
command: "${command}"

# Fixed command with argument interpolation
command: "curl -s https://api.example.com/${endpoint}?format=${format}"

# Static command (no arguments needed)
command: "echo 'Hello from my skill'"
```

### Interpolation Rules

- `${name}` is replaced with the value of the arg named `name`
- Unset optional args with defaults use the default value
- Unset optional args without defaults are replaced with empty string
- Shell metacharacters in argument values are passed through — document safe usage patterns

## Best Practices

### Keep Commands Idempotent

Skills may be retried on failure. Design commands that are safe to run multiple times:

```yaml
# Good — mkdir -p is idempotent
command: "mkdir -p /tmp/output && ${command}"

# Bad — may fail on second run
command: "mkdir /tmp/output && ${command}"
```

### Use Shell-Safe Patterns

```yaml
# Good — quote variables
command: "grep -r \"${query}\" ${directory}"

# Good — use -- to prevent flag injection
command: "echo -- \"${message}\""
```

### Document Examples Clearly

Include realistic examples in the markdown body showing the `command:` field as users would provide it:

```markdown
## Examples

**List items:**
\```
command: "curl -s https://api.example.com/items"
\```

**Search by keyword:**
\```
command: "curl -s 'https://api.example.com/search?q=test'"
\```
```

### Set Appropriate Timeouts

| Use Case | Recommended Timeout |
|----------|-------------------|
| Simple file operations | 5-10s |
| API calls | 15-30s |
| Image/media generation | 60s |
| Large data processing | 120s |

### Tag Consistently

Use existing tags when possible. Common tags:

- `api`, `messaging`, `ai`, `development`, `debugging`
- `image`, `video`, `audio`, `markdown`
- `search`, `notes`, `knowledge-base`
- `meta`, `documentation`

## Validation

Run the validation script to check your SKILL.md files:

```bash
python scripts/validate_skills.py
```

The validator checks:
- Required fields are present
- YAML frontmatter is valid
- Args have `name` and `description`
- `timeout` is a positive integer
- Skill directory name matches `name` field

## Complete Example

```markdown
---
name: weather
description: Get weather forecast for any location
command: 'curl -s "wttr.in/${location}?format=${format}"'
args:
  - name: location
    description: City or location name
    required: false
    default: ""
  - name: format
    description: Output format (1=one-line, 2=day, 3=full, j1=JSON)
    required: false
    default: "3"
tags: [weather, utility, curl]
timeout: 10
---

# Weather Skill

Get weather information using [wttr.in](https://wttr.in).

## Examples

**Get full weather for a city:**
\```
location: "London"
\```

**Get one-line weather summary:**
\```
location: "Zurich"
format: "1"
\```

**Get weather as JSON:**
\```
location: "Berlin"
format: "j1"
\```
```
