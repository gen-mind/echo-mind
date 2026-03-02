---
name: file-edit
description: "Edit files using sed, awk, and other text processing tools"
command: "${command}"
args:
  - name: command
    description: "File editing command (sed, awk, or other text processing)"
    required: true
tags: [file, edit, text, development]
timeout: 30
---

# File Edit Skill

Performs structured file edits using standard Unix text processing tools. Supports sed, awk, Python one-liners, and shell utilities for precise, repeatable file modifications.

## sed Patterns

### Replace Text

```bash
# Replace first occurrence on each line
sed -i 's/old_text/new_text/' file.py

# Replace all occurrences on each line
sed -i 's/old_text/new_text/g' file.py

# Replace only on specific line number
sed -i '5s/old/new/' file.py

# Replace in a line range
sed -i '10,20s/old/new/g' file.py

# Case-insensitive replace
sed -i 's/old/new/gI' file.py
```

### Delete Lines

```bash
# Delete a specific line
sed -i '5d' file.py

# Delete a range of lines
sed -i '10,20d' file.py

# Delete lines matching a pattern
sed -i '/pattern/d' file.py

# Delete blank lines
sed -i '/^$/d' file.py
```

### Insert and Append

```bash
# Insert line before line 5
sed -i '5i\new line content' file.py

# Append line after line 5
sed -i '5a\new line content' file.py

# Insert line before a pattern match
sed -i '/pattern/i\new line before' file.py

# Append line after a pattern match
sed -i '/pattern/a\new line after' file.py
```

### Safe Editing with Backup

```bash
# Create .bak backup before editing
sed -i.bak 's/old/new/g' file.py

# Dry-run: print result without modifying file
sed 's/old/new/g' file.py
```

## awk Patterns

### Field Extraction

```bash
# Print specific columns from CSV
awk -F',' '{print $1, $3}' data.csv

# Print lines where field matches condition
awk -F',' '$2 > 100 {print $0}' data.csv

# Sum a numeric column
awk -F',' '{sum += $3} END {print sum}' data.csv
```

### Filtering and Transformation

```bash
# Print lines matching a pattern
awk '/ERROR/ {print NR": "$0}' app.log

# Transform field values
awk -F'=' '{print $1"="toupper($2)}' config.ini

# Add line numbers
awk '{print NR": "$0}' file.py
```

## Python One-Liners

For complex edits that are awkward in sed/awk:

```bash
# Replace with regex
python3 -c "
import re, pathlib
p = pathlib.Path('file.py')
p.write_text(re.sub(r'pattern', 'replacement', p.read_text()))
"

# JSON field update
python3 -c "
import json, pathlib
p = pathlib.Path('config.json')
d = json.loads(p.read_text())
d['key'] = 'new_value'
p.write_text(json.dumps(d, indent=2) + '\n')
"

# YAML update (requires pyyaml)
python3 -c "
import yaml, pathlib
p = pathlib.Path('config.yaml')
d = yaml.safe_load(p.read_text())
d['setting'] = 'value'
p.write_text(yaml.dump(d, default_flow_style=False))
"
```

## Common Recipes

### Create a New File with Heredoc

```bash
cat > newfile.py << 'EOF'
#!/usr/bin/env python3
"""Module docstring."""


def main():
    pass


if __name__ == "__main__":
    main()
EOF
```

### Append Content to a File

```bash
cat >> file.py << 'EOF'

# New section
def new_function():
    pass
EOF
```

### Replace a Block of Lines

```bash
# Replace lines 10-15 with new content
sed -i '10,15c\
new line 1\
new line 2\
new line 3' file.py
```

### Insert Multiple Lines After Match

```bash
sed -i '/^class MyClass/a\
\    """Class docstring."""\
\
\    def __init__(self):\
\        pass' file.py
```

## Safety Guidelines

- **Always verify before destructive edits**: Use `sed` without `-i` to preview changes
- **Create backups**: Use `sed -i.bak` or `cp file file.bak` before complex edits
- **Test on a single file first**: Before using `find -exec` to edit many files
- **Check exit codes**: Chain with `&& echo "OK" || echo "FAILED"` to confirm success
- **Use single quotes in patterns**: Prevents shell expansion of special characters
