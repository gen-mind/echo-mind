---
name: skill-registry
description: "Browse and manage the EchoMind skill registry (replaces Moltbot's clawdhub)"
command: 'echo "Use the MCP skills_list() and skills_get_info() tools to browse available skills. This skill provides documentation only."'
tags: [meta, skills, registry, documentation]
timeout: 5
---

# EchoMind Skill Registry

Browse, discover, and execute skills registered in the EchoMind MCP Gateway. This is a documentation-only skill that explains how to use the skill system via MCP tools.

## Available MCP Tools

### skills_list()

List all registered skills with their names, descriptions, and tags.

```
skills_list()
```

Returns a list of all available skills including:
- **name** — unique skill identifier
- **description** — what the skill does
- **tags** — categorization tags for filtering

### skills_get_info(name)

Get detailed information about a specific skill, including its arguments, documentation, and usage examples.

```
skills_get_info(name="github")
```

Returns:
- Full skill documentation (from SKILL.md)
- Required and optional arguments
- Command template
- Timeout setting

### skills_execute(name, args)

Execute a skill by name with the provided arguments.

```
skills_execute(name="github", args={"command": "pr list --limit 5"})
```

Returns the command output (stdout/stderr) within the skill's configured timeout.

## Workflow

1. **Discover skills** — call `skills_list()` to see what's available
2. **Learn about a skill** — call `skills_get_info(name)` to read its documentation
3. **Execute a skill** — call `skills_execute(name, args)` with the required arguments

## Tips

- Use tags to find related skills (e.g., filter by "api" or "search")
- Check the skill's timeout before running long operations
- Read the skill documentation for argument formats and examples
