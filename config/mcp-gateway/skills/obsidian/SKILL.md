---
name: obsidian
description: "Manage Obsidian vault files — create, search, and edit markdown notes"
command: "${command}"
args:
  - name: command
    description: "Shell command for Obsidian vault file operations"
    required: true
tags: [obsidian, notes, markdown, knowledge-base]
timeout: 30
max_output_bytes: 131072
---

# Obsidian Skill

Manage Obsidian vault files using standard shell tools. Create, search, and edit markdown notes with frontmatter, wiki-links, and tags. Works on any markdown vault without requiring the Obsidian app.

## Configuration

Set your vault path (default: `~/ObsidianVault`):

```bash
export OBSIDIAN_VAULT=~/ObsidianVault
```

## Find Notes

```bash
# Find all markdown files in vault
find "$OBSIDIAN_VAULT" -name "*.md" -type f

# Find notes by name pattern
find "$OBSIDIAN_VAULT" -name "*meeting*" -type f

# Find recently modified notes (last 7 days)
find "$OBSIDIAN_VAULT" -name "*.md" -type f -mtime -7

# Find notes in a specific folder
find "$OBSIDIAN_VAULT/Daily Notes" -name "*.md" -type f | sort

# Count notes per folder
find "$OBSIDIAN_VAULT" -name "*.md" -type f | sed "s|$OBSIDIAN_VAULT/||" | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn
```

## Search Content

```bash
# Search note contents for a keyword
grep -rl "project alpha" "$OBSIDIAN_VAULT" --include="*.md"

# Search with context (show surrounding lines)
grep -rn -C 2 "TODO" "$OBSIDIAN_VAULT" --include="*.md"

# Find notes with a specific tag
grep -rl "#project" "$OBSIDIAN_VAULT" --include="*.md"

# Find notes linking to a specific note
grep -rl "\[\[Meeting Notes\]\]" "$OBSIDIAN_VAULT" --include="*.md"

# Find all tags used across the vault
grep -roh '#[a-zA-Z0-9_/-]\+' "$OBSIDIAN_VAULT" --include="*.md" | sort | uniq -c | sort -rn
```

## Create Notes

```bash
# Create a new note with frontmatter
cat > "$OBSIDIAN_VAULT/Notes/new-note.md" << 'EOF'
---
title: New Note
date: 2026-02-16
tags: [project, ideas]
---

# New Note

Content goes here.

## Related
- [[Other Note]]
EOF

# Create a daily note
DATE=$(date +%Y-%m-%d)
mkdir -p "$OBSIDIAN_VAULT/Daily Notes"
cat > "$OBSIDIAN_VAULT/Daily Notes/$DATE.md" << EOF
---
date: $DATE
type: daily
---

# $DATE

## Tasks
- [ ]

## Notes

## Links
EOF

# Create a note from template
cp "$OBSIDIAN_VAULT/Templates/meeting.md" "$OBSIDIAN_VAULT/Meetings/$(date +%Y-%m-%d)-standup.md"
```

## Edit Notes

```bash
# Append content to an existing note
echo -e "\n## Update $(date +%Y-%m-%d)\nNew information added." >> "$OBSIDIAN_VAULT/Notes/project.md"

# Add a tag to a note's frontmatter
sed -i 's/^tags: \[/tags: [new-tag, /' "$OBSIDIAN_VAULT/Notes/note.md"

# Replace a wiki-link
sed -i 's/\[\[Old Name\]\]/\[\[New Name\]\]/g' "$OBSIDIAN_VAULT/Notes/note.md"

# Check off a task
sed -i '0,/- \[ \]/s/- \[ \]/- [x]/' "$OBSIDIAN_VAULT/Notes/tasks.md"

# Batch rename a tag across all notes
find "$OBSIDIAN_VAULT" -name "*.md" -exec sed -i 's/#old-tag/#new-tag/g' {} +
```

## List Tags

```bash
# List all unique tags
grep -roh '#[a-zA-Z0-9_/-]\+' "$OBSIDIAN_VAULT" --include="*.md" | sort -u

# List tags from frontmatter
grep -rh "^tags:" "$OBSIDIAN_VAULT" --include="*.md" | sed 's/tags: \[//;s/\]//;s/, /\n/g' | sort | uniq -c | sort -rn
```

## Examples

**Find notes about a topic:**
```
command: "grep -rl 'machine learning' \"$OBSIDIAN_VAULT\" --include='*.md'"
```

**Create a daily note:**
```
command: "mkdir -p \"$OBSIDIAN_VAULT/Daily Notes\" && echo '# '$(date +%Y-%m-%d)'\n\n## Notes\n' > \"$OBSIDIAN_VAULT/Daily Notes/$(date +%Y-%m-%d).md\""
```

**List all tags:**
```
command: "grep -roh '#[a-zA-Z0-9_/-]\\+' \"$OBSIDIAN_VAULT\" --include='*.md' | sort | uniq -c | sort -rn | head -20"
```
