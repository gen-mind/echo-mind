---
name: lobster
description: "Execute multi-step workflows with approval gates and conditional logic"
command: "${command}"
args:
  - name: command
    description: "Workflow step command to execute"
    required: true
tags: [workflow, automation, orchestration, approval]
timeout: 120
max_output_bytes: 131072
---

# Lobster Skill

Execute multi-step workflows with approval gates, conditional logic, and step-by-step orchestration.

## Overview

Lobster provides workflow orchestration for EchoMind's session model. Adapted from Moltbot's lobster extension, it enables sequential execution of steps with checkpoints, conditional branching, output validation between steps, and approval gates. Each workflow step is a command that runs in the sandbox.

## Workflow Patterns

### Sequential Execution

Run steps in order, using the output of one step as input to the next:

```bash
# Step 1: Fetch data
curl -s https://api.example.com/data > /tmp/workflow/step1_output.json

# Step 2: Process data (depends on step 1)
python3 -c "
import json
with open('/tmp/workflow/step1_output.json') as f:
    data = json.load(f)
result = [item for item in data if item['status'] == 'active']
with open('/tmp/workflow/step2_output.json', 'w') as f:
    json.dump(result, f)
print(f'Filtered {len(result)} active items')
"

# Step 3: Generate report (depends on step 2)
python3 -c "
import json
with open('/tmp/workflow/step2_output.json') as f:
    data = json.load(f)
report = '\n'.join(f'- {item[\"name\"]}: {item[\"value\"]}' for item in data)
with open('/tmp/workflow/report.md', 'w') as f:
    f.write(f'# Active Items Report\n\n{report}\n')
print('Report generated at /tmp/workflow/report.md')
"
```

### Conditional Steps

Branch workflow based on intermediate results:

```bash
# Check condition and branch
python3 -c "
import json, sys

with open('/tmp/workflow/step1_output.json') as f:
    data = json.load(f)

count = len(data)
if count > 100:
    print('BRANCH:large_dataset')
    sys.exit(0)
elif count > 0:
    print('BRANCH:normal_dataset')
    sys.exit(0)
else:
    print('BRANCH:empty_dataset')
    sys.exit(0)
"
```

### Output Validation

Validate step output before proceeding:

```bash
# Validate output between steps
python3 -c "
import json, sys

try:
    with open('/tmp/workflow/step2_output.json') as f:
        data = json.load(f)

    # Validate schema
    assert isinstance(data, list), 'Expected list'
    assert len(data) > 0, 'Expected non-empty result'
    for item in data:
        assert 'name' in item, f'Missing name field in {item}'
        assert 'value' in item, f'Missing value field in {item}'

    print(f'VALIDATION:PASS - {len(data)} valid items')
except (AssertionError, json.JSONDecodeError) as e:
    print(f'VALIDATION:FAIL - {e}')
    sys.exit(1)
"
```

### Approval Gates

Pause workflow and output state for user approval:

```bash
# Approval gate — output summary for user review
python3 -c "
import json

with open('/tmp/workflow/step2_output.json') as f:
    data = json.load(f)

print('=== APPROVAL GATE ===')
print(f'Action: Deploy {len(data)} configuration changes')
print(f'Target: production environment')
print()
for i, item in enumerate(data[:10], 1):
    print(f'  {i}. {item[\"name\"]}: {item.get(\"old_value\", \"N/A\")} → {item[\"value\"]}')
if len(data) > 10:
    print(f'  ... and {len(data) - 10} more')
print()
print('=== AWAITING APPROVAL ===')
"
```

### Checkpoint/Resume

Save workflow state for resumption:

```bash
# Save checkpoint
python3 -c "
import json
checkpoint = {
    'current_step': 3,
    'completed_steps': [1, 2],
    'state': {'items_processed': 42, 'errors': 0},
    'outputs': {
        'step1': '/tmp/workflow/step1_output.json',
        'step2': '/tmp/workflow/step2_output.json'
    }
}
with open('/tmp/workflow/checkpoint.json', 'w') as f:
    json.dump(checkpoint, f, indent=2)
print('Checkpoint saved')
"

# Resume from checkpoint
python3 -c "
import json
with open('/tmp/workflow/checkpoint.json') as f:
    cp = json.load(f)
print(f'Resuming from step {cp[\"current_step\"]}')
print(f'Completed: {cp[\"completed_steps\"]}')
print(f'State: {cp[\"state\"]}')
"
```

## Workflow Directory Structure

```
/tmp/workflow/
├── checkpoint.json          # Current workflow state
├── step1_output.json        # Step 1 output
├── step2_output.json        # Step 2 output
├── report.md                # Generated report
└── logs/
    ├── step1.log            # Step 1 execution log
    └── step2.log            # Step 2 execution log
```

## Examples

**Initialize workflow directory and run first step:**
```
command: "mkdir -p /tmp/workflow/logs && curl -s https://api.example.com/data > /tmp/workflow/step1_output.json && echo 'Step 1 complete: data fetched'"
```

**Process data from previous step:**
```
command: "python3 -c \"import json; data = json.load(open('/tmp/workflow/step1_output.json')); filtered = [x for x in data if x.get('active')]; json.dump(filtered, open('/tmp/workflow/step2_output.json', 'w')); print(f'Step 2: filtered to {len(filtered)} items')\""
```

**Validate and generate report:**
```
command: "python3 -c \"import json; data = json.load(open('/tmp/workflow/step2_output.json')); assert len(data) > 0, 'No data'; report = '\\n'.join(f'- {x[\\\"name\\\"]}' for x in data); open('/tmp/workflow/report.md', 'w').write(f'# Report\\n\\n{report}\\n'); print(f'Report generated: {len(data)} items')\""
```

**Save workflow checkpoint:**
```
command: "python3 -c \"import json; json.dump({'step': 2, 'status': 'awaiting_approval', 'output': '/tmp/workflow/report.md'}, open('/tmp/workflow/checkpoint.json', 'w'), indent=2); print('Checkpoint saved — awaiting approval')\""
```

## Notes

- All workflow state is stored in `/tmp/workflow/` within the sandbox
- Each step should write its output to a file for the next step to consume
- Use exit codes to signal success (0) or failure (non-zero)
- Approval gates output a summary and pause — the LLM agent decides whether to proceed
- Checkpoint files enable workflow resumption across sessions
- Validation steps should use assertions with clear error messages
- Long-running workflows should use the 120-second timeout wisely — split into smaller steps
