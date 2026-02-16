---
name: oracle
description: "Bundle and manage CLI prompts for LLM interactions"
command: "${command}"
args:
  - name: command
    description: "oracle command or prompt management command"
    required: true
tags: [prompts, llm, ai, management]
timeout: 30
---

# Oracle Skill

Bundle and manage CLI prompts for LLM interactions. Store, retrieve, list, and template prompts for consistent and reusable LLM workflows.

## Prompt Storage

Prompts are stored as text files in a configurable directory (default: `~/.oracle/prompts/`).

```bash
# Create the prompts directory
mkdir -p ~/.oracle/prompts

# Save a prompt
cat > ~/.oracle/prompts/code-review.md << 'EOF'
Review the following code for:
1. Security vulnerabilities
2. Performance issues
3. Code style and readability
4. Potential bugs

Code:
{{code}}
EOF

# Save a prompt with metadata frontmatter
cat > ~/.oracle/prompts/summarize.md << 'EOF'
---
name: summarize
description: Summarize text to key points
variables: [text, max_points]
---
Summarize the following text into {{max_points}} key bullet points.
Be concise and focus on the most important information.

Text:
{{text}}
EOF
```

## Retrieve Prompts

```bash
# Get a prompt by name
cat ~/.oracle/prompts/code-review.md

# Get just the prompt body (skip frontmatter)
sed -n '/^---$/,/^---$/!p' ~/.oracle/prompts/summarize.md

# Search prompts by keyword
grep -rl "security" ~/.oracle/prompts/
```

## List Prompts

```bash
# List all available prompts
ls -1 ~/.oracle/prompts/*.md | xargs -I{} basename {} .md

# List prompts with descriptions (from frontmatter)
for f in ~/.oracle/prompts/*.md; do
  name=$(basename "$f" .md)
  desc=$(grep -A1 "^description:" "$f" | head -1 | sed 's/description: //')
  printf "%-20s %s\n" "$name" "$desc"
done

# List prompts matching a tag
grep -rl "tags:.*security" ~/.oracle/prompts/
```

## Template Interpolation

```bash
# Simple variable substitution
PROMPT=$(cat ~/.oracle/prompts/code-review.md)
CODE=$(cat myfile.py)
echo "${PROMPT//\{\{code\}\}/$CODE}"

# Multi-variable substitution with sed
cat ~/.oracle/prompts/summarize.md \
  | sed "s/{{max_points}}/5/g" \
  | sed "s/{{text}}/$(cat input.txt | sed 's/[&/\]/\\&/g')/g"

# Using envsubst for ${VAR} style templates
export TEXT="Hello world"
export MAX_POINTS=3
envsubst < ~/.oracle/prompts/summarize.md
```

## Organize Prompts

```bash
# Create categorized prompt directories
mkdir -p ~/.oracle/prompts/{coding,writing,analysis}

# Move prompts to categories
mv ~/.oracle/prompts/code-review.md ~/.oracle/prompts/coding/

# Find all prompts recursively
find ~/.oracle/prompts -name "*.md" -type f

# Count prompts by category
find ~/.oracle/prompts -name "*.md" -type f | sed 's|/[^/]*$||' | sort | uniq -c
```

## Examples

**List all prompts:**
```
command: "ls -1 ~/.oracle/prompts/*.md 2>/dev/null | xargs -I{} basename {} .md || echo 'No prompts found. Create ~/.oracle/prompts/ first.'"
```

**Create a new prompt:**
```
command: "mkdir -p ~/.oracle/prompts && cat > ~/.oracle/prompts/explain.md << 'PROMPT'\nExplain the following concept in simple terms:\n\n{{topic}}\nPROMPT"
```

**Search prompts:**
```
command: "grep -rl 'review' ~/.oracle/prompts/ 2>/dev/null | xargs -I{} basename {} .md"
```
