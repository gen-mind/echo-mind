---
name: coding-agent
description: "Execute shell commands for coding, building, testing, and development tasks"
command: "${command}"
args:
  - name: command
    description: "Shell command to execute (e.g., 'python -m pytest tests/', 'npm run build')"
    required: true
tags: [coding, development, build, test]
timeout: 120
max_output_bytes: 262144
---

# Coding Agent Skill

Executes shell commands for a wide range of software development tasks including testing, building, linting, file operations, git workflows, and environment inspection.

## Usage Patterns

### Running Tests

```bash
# Python tests
python -m pytest tests/ -v
python -m pytest tests/unit/ -k "test_auth" --tb=short
python -m pytest tests/ --cov=src --cov-report=term-missing

# Node.js tests
npm test
npm run test -- --coverage
npx jest tests/api.test.ts

# Go tests
go test ./... -v
go test -race -count=1 ./pkg/...
```

### Building Projects

```bash
# Python
pip install -e . && python setup.py check

# Node.js
npm run build
npm run build && npm run typecheck

# Make-based projects
make build
make clean && make all

# Rust
cargo build --release

# Docker
docker build -t myapp .
```

### Linting and Formatting

```bash
# Python
ruff check src/
ruff format --check src/
mypy src/ --strict

# JavaScript/TypeScript
npx eslint src/ --fix
npx prettier --check "src/**/*.ts"

# Go
golangci-lint run ./...
gofmt -l .
```

### File Operations

```bash
# Search for files
find src/ -name "*.py" -type f
ls -la src/api/

# Count lines
wc -l src/**/*.py
find . -name "*.ts" | xargs wc -l | tail -1

# Search file contents
grep -rn "TODO" src/
grep -rn "def process" src/ --include="*.py"
```

### Git Operations

```bash
# Status and history
git status
git log --oneline -10
git diff HEAD~1

# Branch operations
git branch -a
git log --oneline main..HEAD

# Inspection
git show HEAD --stat
git blame src/api/main.py
```

### Package Management

```bash
# Python
pip install -r requirements.txt
pip list --outdated
pip show pandas

# Node.js
npm install
npm ls --depth=0
npm outdated
```

### Environment Inspection

```bash
# System info
python --version
node --version
which python

# Environment variables
env | grep DATABASE
echo $PATH
```

### Multi-Step Commands

Chain commands with `&&` for sequential execution:

```bash
# Install, lint, then test
pip install -r requirements.txt && ruff check src/ && python -m pytest tests/ -v

# Build and verify
npm run build && npm run typecheck && npm test

# Clean, build, and test
make clean && make build && make test
```

## Guidelines

- Commands run in the project working directory
- Use `&&` to chain dependent commands (second runs only if first succeeds)
- Use `;` to chain independent commands (all run regardless of exit codes)
- Timeout is 120 seconds — long-running processes may be killed
- Output is capped at 256 KB — pipe through `tail` or `head` for large outputs
