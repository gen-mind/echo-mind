# Skills Migration Analysis: 30 Native Tools → Moltbot-Style Bash Skills

> **Status**: Analysis complete | **Confidence**: High
> **Decision**: Replace all 30 native Python tools with Moltbot-style SKILL.md bash skills exposed via MCP server.

---

## 1. Current EchoMind Tool Inventory (30 Native Python Tools)

All tools are in `src/agent/tools/` as factory functions returning callables. They use `subprocess.run()` for CLI operations and Python stdlib for file operations.

### Tool Catalog by Category

| # | Tool Name | Category | Approval | Implementation Pattern | Essential? |
|---|-----------|----------|----------|----------------------|------------|
| 1 | `read` | Filesystem | never | Python `open()` + line numbering | **Essential** |
| 2 | `write` | Filesystem | always | Python `open()` + `mkdir(parents=True)` | **Essential** |
| 3 | `grep` | Filesystem | never | `subprocess.run(["rg", ...])` | **Essential** |
| 4 | `glob` | Filesystem | never | Python `Path.glob()` | **Essential** |
| 5 | `edit` | Edit | always | Python string `replace()` + `difflib` | **Essential** |
| 6 | `list_dir` | Directory | never | Python `Path.iterdir()` + formatting | Nice-to-have |
| 7 | `tree` | Directory | never | Python recursive walk + ASCII art | Nice-to-have |
| 8 | `mkdir` | Directory | never | Python `Path.mkdir(parents=True)` | Nice-to-have |
| 9 | `move` | Directory | always | Python `shutil.move()` | Nice-to-have |
| 10 | `delete` | Directory | always | Python `shutil.rmtree()` / `unlink()` | Nice-to-have |
| 11 | `bash` | Execution | always | `subprocess.run(command, shell=True)` | **Essential** |
| 12 | `http_request` | Web | never | Python `urllib.request` | Nice-to-have |
| 13 | `git_log` | Git | never | `subprocess.run("git log ...")` | Nice-to-have |
| 14 | `git_diff` | Git | never | `subprocess.run("git diff ...")` | Nice-to-have |
| 15 | `git_status` | Git | never | `subprocess.run("git status")` | Nice-to-have |
| 16 | `git_add` | Git | always | `subprocess.run("git add ...")` | Nice-to-have |
| 17 | `git_commit` | Git | always | `subprocess.run("git commit ...")` | Nice-to-have |
| 18 | `git_branch` | Git (ext) | never | `subprocess.run("git branch ...")` | Nice-to-have |
| 19 | `git_checkout` | Git (ext) | always | `subprocess.run("git checkout ...")` | Nice-to-have |
| 20 | `git_stash` | Git (ext) | never | `subprocess.run("git stash ...")` | Nice-to-have |
| 21 | `git_push` | Git (ext) | always | `subprocess.run("git push ...")` | Nice-to-have |
| 22 | `git_pull` | Git (ext) | always | `subprocess.run("git pull ...")` | Nice-to-have |
| 23 | `git_reset` | Git (ext) | always | `subprocess.run("git reset ...")` | Nice-to-have |
| 24 | `git_clone` | Git (ext) | never | `subprocess.run("git clone ...")` | Nice-to-have |
| 25 | `git_tag` | Git (ext) | never | `subprocess.run("git tag ...")` | Nice-to-have |
| 26 | `env_get` | System | never | Python `os.environ.get()` | Nice-to-have |
| 27 | `which` | System | never | Python `shutil.which()` | Nice-to-have |
| 28 | `find_replace` | System | always | Python `re.sub()` across files | Nice-to-have |
| 29 | `diff` | Text | never | Python `difflib.unified_diff()` | Nice-to-have |
| 30 | `patch` | Text | always | System `patch` or manual hunk parser | Nice-to-have |

### Key Insight: Most Tools Are Thin Shell Wrappers

**22 of 30 tools** (73%) are essentially wrappers around CLI commands. The 13 git tools literally do `subprocess.run("git <command> ...")`. The grep tool shells out to `rg`. Only 8 tools use Python-native operations (read, write, glob, edit, list_dir, tree, mkdir, env_get), and even these have trivial bash equivalents.

### Approval Mode Distribution

- **always_require** (destructive): 12 tools — write, edit, move, delete, bash, git_add, git_commit, git_checkout, git_push, git_pull, git_reset, find_replace, patch
- **never_require** (safe): 18 tools — all read-only operations

---

## 2. Moltbot Skill Architecture Deep Dive

### How Moltbot Skills Work

Moltbot uses a **progressive disclosure** model:

1. **Metadata layer** (always in context): skill `name` + `description` (~100 words per skill). The LLM uses this to decide which skills to invoke.
2. **Instructions layer** (loaded on trigger): Full SKILL.md body with bash examples, workflows, and guidance. Loaded into context only when the LLM determines the skill is relevant.
3. **Resources layer** (on-demand): `scripts/`, `references/`, `assets/` directories. Loaded only when the LLM explicitly reads them.

### SKILL.md File Format Specification

```yaml
---
name: skill-name                    # Required: lowercase, hyphens, <=64 chars
description: "What this skill does" # Required: primary trigger for skill selection
homepage: https://example.com       # Optional: reference URL
metadata: {"moltbot":{"emoji":"🔧","requires":{"bins":["tool-name"]},"install":[...]}}
                                    # Optional: platform requirements, install instructions
---

# Skill Title

## Instructions (Markdown body)
- Bash examples for how to use the underlying CLI tool
- Workflow guidance
- Tips and troubleshooting
```

### Metadata Schema (from `types.ts`)

```typescript
type MoltbotSkillMetadata = {
  always?: boolean;          // Always load into context
  emoji?: string;            // Display emoji
  homepage?: string;         // Reference URL
  os?: string[];             // Platform restriction ["darwin", "linux"]
  requires?: {
    bins?: string[];          // ALL of these must be present
    anyBins?: string[];       // ANY of these must be present
    env?: string[];           // Required environment variables
    config?: string[];        // Required config paths
  };
  install?: SkillInstallSpec[]; // How to install dependencies
};
```

### Skill Loading Flow (from `skills/workspace.ts` + `skills/frontmatter.ts`)

1. `loadWorkspaceSkillEntries()` scans workspace skill directories
2. Parses YAML frontmatter via `parseFrontmatter()`
3. Resolves Moltbot-specific metadata via `resolveMoltbotMetadata()`
4. Builds eligibility context (local bins + remote node bins)
5. `filterWorkspaceSkillEntries()` filters by platform, required bins, env vars
6. `buildWorkspaceSkillsPrompt()` generates system prompt section with skill metadata
7. On skill trigger, full SKILL.md body is loaded into context

### Key Design Principle: LLM Learns Bash Organically

Moltbot does NOT give the LLM a structured tool call for each operation. Instead:
- The LLM has a general-purpose `bash` tool
- Skills teach the LLM **how to use specific CLI tools** via bash
- The LLM constructs bash commands itself based on skill instructions

**Example**: The `github` skill doesn't provide `git_status`, `git_add`, etc. tools. It teaches: "Use `gh pr checks 55 --repo owner/repo`" — and the LLM runs that via `bash`.

---

## 3. All 53 Moltbot Skills by Category

### Category 1: Messaging & Communication (9 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `slack` | Slack via custom tool (not bash) | **No** — Moltbot-specific tool |
| `discord` | Discord interactions | **No** — Moltbot-specific |
| `bluebubbles` | iMessage via BlueBubbles API | **No** — platform-specific |
| `imsg` | iMessage via AppleScript | **No** — macOS only |
| `wacli` | WhatsApp via CLI | **No** — Moltbot-specific |
| `himalaya` | Email via himalaya CLI | **Yes** — generic CLI |
| `voice-call` | Voice calls | **No** — Moltbot-specific |
| `blucli` | BlueBubbles CLI | **No** — platform-specific |
| `bird` | Bluesky via `bird` CLI | **Yes** — generic CLI |

### Category 2: Developer Tools (6 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `coding-agent` | Run Codex/Claude/Pi agents | **Yes** — generic bash |
| `github` | GitHub via `gh` CLI | **Yes** — generic CLI |
| `tmux` | tmux session management | **Yes** — generic CLI |
| `session-logs` | Search session JSONL logs | **Partial** — format-specific |
| `model-usage` | Track model usage/costs | **No** — Moltbot-specific |
| `mcporter` | MCP tool management | **Partial** — concept portable |

### Category 3: Notes & Knowledge (4 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `obsidian` | Obsidian vault via `obsidian-cli` | **Yes** — generic CLI |
| `bear-notes` | Bear notes via AppleScript | **No** — macOS only |
| `apple-notes` | Apple Notes via AppleScript | **No** — macOS only |
| `notion` | Notion via API | **Yes** — generic CLI |

### Category 4: Media & Content (8 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `nano-pdf` | PDF editing via `nano-pdf` CLI | **Yes** — generic CLI |
| `nano-banana-pro` | Image editing | **Yes** — generic CLI |
| `openai-image-gen` | Image generation via OpenAI API | **Yes** — generic CLI |
| `openai-whisper` | Local Whisper transcription | **Yes** — generic CLI |
| `openai-whisper-api` | Whisper API transcription | **Yes** — generic CLI |
| `video-frames` | Video frame extraction | **Yes** — generic CLI |
| `camsnap` | Camera snapshot | **No** — macOS-specific |
| `peekaboo` | Screenshot tool | **No** — macOS-specific |

### Category 5: Smart Home & IoT (3 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `openhue` | Philips Hue via `openhue` CLI | **Yes** — generic CLI |
| `sonoscli` | Sonos via CLI | **Yes** — generic CLI |
| `spotify-player` | Spotify via `spotify_player` CLI | **Yes** — generic CLI |

### Category 6: Web & Search (5 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `weather` | Weather via `curl wttr.in` | **Yes** — pure bash |
| `summarize` | URL/video summarization | **Yes** — generic CLI |
| `blogwatcher` | Blog feed monitoring | **Partial** — needs adaptation |
| `gifgrep` | GIF search | **Yes** — generic CLI |
| `goplaces` | Location search | **Yes** — generic CLI |

### Category 7: Task Management (3 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `apple-reminders` | Apple Reminders via AppleScript | **No** — macOS only |
| `things-mac` | Things 3 via `things-cli` | **No** — macOS only |
| `trello` | Trello via API | **Yes** — generic CLI |

### Category 8: AI & Agents (5 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `gemini` | Gemini API interaction | **Yes** — generic CLI |
| `oracle` | Knowledge base queries | **Partial** — concept portable |
| `sag` | Search-augmented generation | **Partial** — concept portable |
| `clawdhub` | Skill marketplace | **No** — Moltbot-specific |
| `skill-creator` | Skill authoring guide | **Yes** — directly reusable |

### Category 9: Security & Admin (3 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `1password` | 1Password via `op` CLI | **Yes** — generic CLI |
| `food-order` | Food ordering | **No** — specific service |
| `eightctl` | System management | **Partial** — needs adaptation |

### Category 10: Presentation & Canvas (3 skills)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `canvas` | HTML display on nodes | **No** — Moltbot-specific |
| `songsee` | Song recognition | **Yes** — generic CLI |
| `local-places` | Local places server | **Yes** — generic CLI |

### Category 11: Text Processing (1 skill)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `sherpa-onnx-tts` | Text-to-speech via ONNX | **Yes** — generic CLI |

### Category 12: Order & Commerce (1 skill)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `ordercli` | Order management CLI | **Yes** — generic CLI |

### Category 13: Gaming (1 skill)
| Skill | Description | Portable? |
|-------|-------------|-----------|
| `gog` | GOG game management | **Yes** — generic CLI |

### Portability Summary

| Portability | Count | % |
|-------------|-------|---|
| **Yes** (directly portable) | 27 | 51% |
| **Partial** (needs adaptation) | 7 | 13% |
| **No** (Moltbot/platform-specific) | 19 | 36% |

---

## 4. Migration Mapping: 30 EchoMind Tools → Skill Equivalents

### Core Principle

With a `bash` tool available, the LLM can do everything the 30 native tools do — and more. Skills teach it _how_ and provide guardrails.

### Mapping Table

| EchoMind Tool | Bash Equivalent | Skill Needed? | Notes |
|---------------|-----------------|---------------|-------|
| **Filesystem (4)** | | | |
| `read` | `cat -n file \| head -n $limit` | No — bash built-in | System prompt teaches cat/head usage |
| `write` | `cat > file << 'EOF'` | No — bash built-in | System prompt teaches heredoc pattern |
| `grep` | `rg pattern path --glob '*.py'` | No — bash built-in | System prompt teaches rg usage |
| `glob` | `find . -name '*.py'` or `fd` | No — bash built-in | System prompt teaches find/fd usage |
| **Edit (1)** | | | |
| `edit` | `sed -i 's/old/new/g' file` | **Yes** — `file-edit` skill | Structured edit is safer than sed; consider keeping as native |
| **Directory (5)** | | | |
| `list_dir` | `ls -la` | No — bash built-in | |
| `tree` | `tree -L 3` | No — bash built-in | Requires `tree` binary |
| `mkdir` | `mkdir -p path` | No — bash built-in | |
| `move` | `mv source dest` | No — bash built-in | |
| `delete` | `rm -rf path` | No — bash built-in | Dangerous! Needs approval policy |
| **Execution (1)** | | | |
| `bash` | N/A — IS the bash tool | **Core** | This becomes the PRIMARY tool |
| **Web (1)** | | | |
| `http_request` | `curl -s url` | No — bash built-in | System prompt teaches curl patterns |
| **Git Core (5)** | | | |
| `git_log` | `git log --oneline -10` | **Yes** — `github` skill | Skill teaches git CLI patterns |
| `git_diff` | `git diff` | Via `github` skill | |
| `git_status` | `git status` | Via `github` skill | |
| `git_add` | `git add files` | Via `github` skill | |
| `git_commit` | `git commit -m "msg"` | Via `github` skill | |
| **Git Extended (8)** | | | |
| `git_branch` | `git branch -a` | Via `github` skill | |
| `git_checkout` | `git checkout branch` | Via `github` skill | |
| `git_stash` | `git stash push/pop` | Via `github` skill | |
| `git_push` | `git push origin branch` | Via `github` skill | |
| `git_pull` | `git pull origin branch` | Via `github` skill | |
| `git_reset` | `git reset --mixed .` | Via `github` skill | |
| `git_clone` | `git clone url` | Via `github` skill | |
| `git_tag` | `git tag -l` | Via `github` skill | |
| **System (3)** | | | |
| `env_get` | `echo $VAR_NAME` | No — bash built-in | Need to block sensitive vars differently |
| `which` | `which command` | No — bash built-in | |
| `find_replace` | `rg pattern -l \| xargs sed` | No — bash built-in | Or skill with safer multi-file edit |
| **Text (2)** | | | |
| `diff` | `diff -u file_a file_b` | No — bash built-in | |
| `patch` | `patch < diff.patch` | No — bash built-in | |

### What We Gain

1. **Unlimited tool surface**: Any CLI tool is immediately usable. No need to write Python wrappers.
2. **Composability**: The LLM can pipe commands (`rg pattern | head -5 | wc -l`).
3. **Community skills**: 27 Moltbot skills are directly portable.
4. **Simpler codebase**: Delete ~1100 lines of Python tool code, replace with SKILL.md files.
5. **User-extensible**: Users can add skills by dropping SKILL.md files.

### What We Lose

1. **Structured parameters**: Native tools have typed JSON schema params. Bash is free-form text.
2. **Safety guardrails**: Native tools prevent `rm .git`, block sensitive env vars, limit `--force`. Bash has no built-in guardrails.
3. **Output formatting**: Native tools return structured, truncated output. Bash returns raw text.
4. **Approval granularity**: Current tools have per-tool approval modes. Bash is all-or-nothing (unless we add command analysis).

### Mitigation Strategy

| Risk | Mitigation |
|------|-----------|
| No structured params | Skills teach correct usage patterns; LLM is smart enough |
| Safety | Sandbox container provides hard boundary (Phase 1). Policy engine adds command-level approval (Phase 2) |
| Raw output | Bash tool truncates at 10K chars (already implemented). Skills teach output filtering (`\| head`, `\| jq`) |
| Approval | MCP server can analyze command before execution and apply approval rules |

---

## 5. Skill-as-MCP-Tool Pattern

### Architecture

```
┌────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  EchoMind      │     │  MCP Skills      │     │  Docker          │
│  Agent         │────▶│  Server          │────▶│  Sandbox         │
│  (SK kernel)   │ MCP │  (Python)        │exec │  (gVisor)        │
│                │     │                  │     │                  │
│  System prompt │     │  Reads SKILL.md  │     │  bash execution  │
│  includes skill│     │  files at start  │     │  in isolated env │
│  metadata      │     │  Registers as    │     │                  │
│                │     │  MCP tools       │     │                  │
└────────────────┘     └──────────────────┘     └──────────────────┘
```

### How It Works

1. **Startup**: MCP Skills Server scans `skills/` directory for SKILL.md files
2. **Registration**: Each skill becomes an MCP tool with:
   - `name`: from SKILL.md frontmatter
   - `description`: from SKILL.md frontmatter
   - `inputSchema`: `{ command: string, workdir?: string, timeout?: number }`
3. **Agent system prompt**: Includes skill metadata (name + description) so the LLM knows what's available
4. **Invocation**: Agent calls MCP tool → server validates → executes bash in sandbox → returns result
5. **Context enrichment**: On first use of a skill, the full SKILL.md body can be injected into context

### MCP Server Pseudo-Implementation

```python
class SkillsMCPServer:
    """MCP server that exposes SKILL.md files as tools."""

    def __init__(self, skills_dir: str):
        self.skills = self._load_skills(skills_dir)

    def _load_skills(self, skills_dir: str) -> dict[str, SkillDefinition]:
        """Parse all SKILL.md files into tool definitions."""
        skills = {}
        for skill_dir in Path(skills_dir).iterdir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, body = parse_frontmatter(skill_md.read_text())
                skills[frontmatter["name"]] = SkillDefinition(
                    name=frontmatter["name"],
                    description=frontmatter["description"],
                    body=body,
                    scripts_dir=skill_dir / "scripts",
                    requires=parse_metadata(frontmatter.get("metadata")),
                )
        return skills

    def list_tools(self) -> list[Tool]:
        """MCP list_tools handler."""
        return [
            Tool(
                name=f"skill_{skill.name}",
                description=skill.description,
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Bash command to execute"},
                        "workdir": {"type": "string", "description": "Working directory"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                    },
                    "required": ["command"],
                },
            )
            for skill in self.skills.values()
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        """MCP call_tool handler — executes command in sandbox."""
        skill_name = name.removeprefix("skill_")
        skill = self.skills.get(skill_name)
        if not skill:
            return f"Unknown skill: {skill_name}"

        return await self.sandbox.execute(
            command=arguments["command"],
            workdir=arguments.get("workdir"),
            timeout=arguments.get("timeout", 30),
        )
```

### Comparison: Moltbot Direct vs EchoMind MCP

| Aspect | Moltbot (Direct) | EchoMind (via MCP) |
|--------|------------------|-------------------|
| Bash execution | Direct `subprocess` | MCP call → sandbox container |
| Latency | ~1ms overhead | ~10-50ms overhead (MCP + container) |
| Security | Sandbox optional | Sandbox mandatory (gVisor) |
| Skill loading | Built-in to runtime | MCP server reads SKILL.md at startup |
| Tool schema | Minimal (bash tool) | Per-skill MCP tool registration |
| Context injection | Skill body → system prompt | Same pattern via MCP resources |

**Verdict**: The MCP indirection adds ~10-50ms latency per call. This is negligible for most operations. The security benefit of mandatory sandbox execution outweighs the cost.

---

## 6. Feasibility Assessment

### Scorecard

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Technical feasibility** | 9/10 | All 30 tools have trivial bash equivalents |
| **Copy Moltbot skills directly** | 7/10 | 27/53 skills are directly portable; 7 need minor adaptation |
| **Safety parity** | 6/10 | Need sandbox + command analysis to match native tool safety |
| **LLM compatibility** | 9/10 | Claude/GPT are excellent at bash; skills teach patterns |
| **Development effort** | 8/10 | Delete ~1100 LOC Python, write ~200 LOC MCP server + skill files |
| **Maintenance cost** | 9/10 | SKILL.md files are trivial to maintain vs Python tool code |

### Critical Path Items

1. **Sandbox must exist first** — Without sandbox, bash tool is too dangerous for production
2. **MCP Skills Server** — New component (~200 LOC) to bridge SKILL.md files to MCP protocol
3. **System prompt engineering** — Teach the LLM bash patterns for core operations (read, write, edit)
4. **Approval policy** — Command-level approval (e.g., block `rm -rf /`, `git push --force`)

### Can We Literally Copy Moltbot SKILL.md Files?

**Yes, with caveats:**

| Aspect | Copy directly? | Adaptation needed? |
|--------|---------------|-------------------|
| Frontmatter format | Yes | None — same YAML format |
| Bash examples | Yes | None — bash is bash |
| `requires.bins` | Yes | Need bin-check at EchoMind level |
| `install` specs | Partial | Need our own installer or skip |
| Platform gating (`os`) | Yes | Same `["darwin", "linux"]` |
| Moltbot-specific features | No | Remove references to moltbot gateway, nodes, etc. |
| References to Moltbot tools (slack, canvas) | No | Skip or adapt to EchoMind equivalents |

---

## 7. Priority Implementation Plan

### Phase 1: Core Skills (Replace 30 tools)

These skills replace the native Python tools. They are system-level and always available.

| Priority | Skill | Replaces | Effort |
|----------|-------|----------|--------|
| P0 | `bash` | execution.bash | Already exists — enhance with sandbox |
| P0 | System prompt | All 30 tools | Teach bash patterns for file/git/search ops |
| P1 | `file-edit` | edit, find_replace | Structured edit skill with sed/awk patterns |
| P1 | `github` | All 13 git tools | Copy from Moltbot + add EchoMind patterns |

### Phase 2: High-Value Moltbot Skills (Copy & Adapt)

| Priority | Skill | Value for EchoMind |
|----------|-------|--------------------|
| P1 | `coding-agent` | Run sub-agents (Codex, Claude) for complex tasks |
| P1 | `tmux` | Multi-agent orchestration |
| P1 | `summarize` | URL/video summarization for RAG |
| P2 | `obsidian` | Note management integration |
| P2 | `nano-pdf` | PDF processing for document pipeline |
| P2 | `weather` | Simple utility, good test case |
| P2 | `1password` | Secrets management |
| P3 | `openai-whisper` | Audio transcription |
| P3 | `openai-image-gen` | Image generation |
| P3 | `skill-creator` | Meta-skill for creating new skills |

### Phase 3: EchoMind-Specific Skills (New)

| Skill | Description |
|-------|-------------|
| `echomind-search` | RAG search via EchoMind API |
| `echomind-documents` | Document management via API |
| `echomind-connectors` | Connector management via API |
| `echomind-memory` | Agent memory operations |
| `echomind-admin` | System administration |

---

## 8. SKILL.md Format for EchoMind

### Standard Template

```yaml
---
name: skill-name
description: "Clear description of what this skill does and when to use it."
metadata: {"echomind":{"emoji":"🔧","requires":{"bins":["tool-name"]}}}
---

# Skill Title

## Quick Start

```bash
# Most common usage pattern
tool-name command --flag value
```

## Commands

| Command | Description |
|---------|-------------|
| `tool-name action` | What it does |

## Examples

### Example: Specific Use Case
```bash
tool-name specific-command --with flags
```

## Tips
- Important gotchas
- Best practices
```

### EchoMind Metadata Extension

```json
{
  "echomind": {
    "emoji": "🔧",
    "category": "developer",
    "approval": "always_require",
    "requires": {
      "bins": ["rg"],
      "sandbox": true
    }
  }
}
```

Key differences from Moltbot:
- `approval` field: maps to policy engine approval mode
- `sandbox` field: whether command must run in sandbox (default: true)
- `category` field: for skill organization in UI

---

## 9. What Stays Native (Not Migrated to Skills)

Some operations should remain as native Python tools exposed directly (not via skills):

| Operation | Why Native? |
|-----------|-------------|
| `edit` (search-and-replace) | Structured params prevent off-by-one errors. Safer than `sed`. Consider keeping alongside bash. |
| EchoMind API calls | Internal gRPC/API calls shouldn't go through bash |
| Memory operations | Agent memory is an internal data structure |

**Recommendation**: Keep `edit` as a native tool AND provide a `file-edit` skill. Let the agent choose based on context. All other tools can be fully replaced by bash + skills.

---

## 10. Summary & Recommendation

### Decision: Proceed with Migration

| Aspect | Assessment |
|--------|-----------|
| Feasibility | **High** — 73% of tools are already shell wrappers |
| Risk | **Medium** — sandbox required for safety parity |
| Effort | **Low** — delete 1100 LOC, write ~200 LOC MCP server + skill files |
| Benefit | **High** — unlimited tool surface, community skills, user extensibility |
| Alignment | **High** — matches Moltbot patterns for future skill sharing |

### Execution Order

1. Build sandbox container (Phase 1 prerequisite)
2. Build MCP Skills Server (~200 LOC)
3. Write system prompt teaching bash patterns for core operations
4. Port `github` skill from Moltbot
5. Delete 29 of 30 native tools (keep `edit` as optional native)
6. Port high-value Moltbot skills (coding-agent, tmux, summarize)
7. Build EchoMind-specific skills (search, documents, connectors)

### Files to Delete After Migration

```
src/agent/tools/filesystem.py    # read, write, grep, glob → bash
src/agent/tools/directory.py     # list_dir, tree, mkdir, move, delete → bash
src/agent/tools/git.py           # git_log, git_diff, git_status, git_add, git_commit → bash
src/agent/tools/git_extended.py  # git_branch..git_tag → bash
src/agent/tools/system.py        # env_get, which, find_replace → bash
src/agent/tools/text.py          # diff, patch → bash
src/agent/tools/web.py           # http_request → bash (curl)
```

**Keep**: `src/agent/tools/edit.py` (optional native), `src/agent/tools/execution.py` (bash core), `src/agent/tools/registry.py` (simplified)

---

## 11. SKILL.md Format Specification (Formal)

This section defines the complete, formal SKILL.md format for EchoMind skills. The format is compatible with the Moltbot/OpenClaw SKILL.md convention and the Anthropic Agent Skills standard, with EchoMind-specific extensions.

### 11.1 File Structure

Every skill is a directory containing at minimum a `SKILL.md` file:

```
config/skills/
  github/
    SKILL.md              # Required: metadata + instructions
    scripts/              # Optional: helper scripts
    assets/               # Optional: reference data
  weather/
    SKILL.md
  file-edit/
    SKILL.md
    scripts/
      safe-sed.sh         # Optional: helper script
```

### 11.2 YAML Frontmatter Fields

The frontmatter block is delimited by `---` lines at the top of the file. All fields use YAML syntax.

#### Required Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `name` | string | `^[a-z0-9-]+$`, 1-64 chars, no leading/trailing/consecutive hyphens | Unique skill identifier. Must match the containing directory name. |
| `description` | string | 1-1024 chars, no angle brackets | What the skill does AND when to trigger it. This is the primary signal the LLM uses to decide whether to invoke the skill. |

#### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | string | `"1.0.0"` | Semantic version of the skill. |
| `author` | string | `null` | Skill author (for community skills). |
| `homepage` | string (URL) | `null` | Reference URL surfaced in skill listing. |
| `license` | string | `null` | License identifier (e.g., `"Apache-2.0"`). |
| `tags` | list[string] | `[]` | Category tags for filtering and discovery (e.g., `["git", "developer", "vcs"]`). |
| `metadata` | JSON object (single-line) | `{}` | EchoMind-specific configuration (see section 11.3). |

#### EchoMind Metadata Extension

The `metadata` field is a single-line JSON object (required by the frontmatter parser to avoid YAML multiline ambiguity). It contains an `echomind` key with the following sub-fields:

```json
{
  "echomind": {
    "emoji": "string",
    "category": "string",
    "approval": "string",
    "timeout": "integer",
    "output_limit": "integer",
    "requires": {
      "bins": ["string"],
      "any_bins": ["string"],
      "env": ["string"]
    },
    "os": ["string"]
  }
}
```

| Sub-field | Type | Default | Description |
|-----------|------|---------|-------------|
| `emoji` | string | `"🔧"` | Display emoji for the skill in UI and logs. |
| `category` | string | `"general"` | Skill category: `developer`, `search`, `media`, `system`, `communication`, `general`. |
| `approval` | string | `"never_require"` | Approval mode: `"always_require"` or `"never_require"`. Maps to the policy engine. |
| `timeout` | int | `30` | Default execution timeout in seconds. Overridable per call up to the trust-level maximum. |
| `output_limit` | int | `65536` | Maximum output bytes (64 KB default). Truncated with a warning if exceeded. |
| `requires.bins` | list[string] | `[]` | ALL of these binaries must be present on PATH for the skill to be eligible. |
| `requires.any_bins` | list[string] | `[]` | ANY one of these binaries must be present (OR logic). |
| `requires.env` | list[string] | `[]` | Required environment variables (managed by MCP gateway, never exposed to agent). |
| `os` | list[string] | `[]` | Platform restriction. Empty = all platforms. Values: `"linux"`, `"darwin"`. |

### 11.3 Markdown Body Structure

The body follows the YAML frontmatter. It has no formal structural restrictions, but the recommended pattern is:

```markdown
# Skill Title

Brief overview of what this skill provides.

## Quick Start

Most common usage pattern (1-3 bash examples).

## Commands

Reference table of available commands/subcommands.

## Examples

Concrete examples organized by use case.

## Tips

Gotchas, best practices, edge cases.
```

**Guidelines:**
- Keep the body under 500 lines (~5,000 words). The agent reads the entire body when the skill is loaded.
- Use `{baseDir}` to reference the skill's own directory (for scripts/assets).
- Provide real, working bash commands. The agent will copy and adapt them.
- Include error handling patterns (what to do when a command fails).
- State clearly which commands are safe (read-only) and which are destructive.

### 11.4 Example SKILL.md Files

#### Example 1: Simple Skill (weather)

```yaml
---
name: weather
description: "Get weather forecasts and current conditions for any location. Use when the user asks about weather, temperature, or forecasts."
version: "1.0.0"
tags: ["weather", "utility"]
metadata: {"echomind":{"emoji":"🌤️","category":"general","approval":"never_require","timeout":10}}
---

# Weather

Get weather information using wttr.in (no API key needed).

## Quick Start

```bash
# Current weather for a city
curl -s "wttr.in/Zurich?format=3"

# Detailed forecast
curl -s "wttr.in/Zurich"

# Specific format (one-liner)
curl -s "wttr.in/Zurich?format=%l:+%c+%t+(%f)+%h+%w"
```

## Commands

| Command | Description |
|---------|-------------|
| `curl -s "wttr.in/CITY"` | Full forecast (3 days) |
| `curl -s "wttr.in/CITY?format=3"` | One-line summary |
| `curl -s "wttr.in/CITY?0"` | Current conditions only |
| `curl -s "wttr.in/CITY?format=j1"` | JSON output for parsing |

## Tips

- URL-encode city names with spaces: `wttr.in/New+York`
- Use `?lang=de` for German output
- Pipe through `head -7` for compact output
```

#### Example 2: Complex Skill with Approval (github)

```yaml
---
name: github
description: "Git version control and GitHub operations. Use for any git commands (status, diff, log, commit, push, pull, branch) or GitHub operations (PRs, issues, releases). Covers all repository management tasks."
version: "1.0.0"
tags: ["git", "github", "developer", "vcs"]
metadata: {"echomind":{"emoji":"🐙","category":"developer","approval":"always_require","timeout":60,"requires":{"bins":["git"],"any_bins":["gh"]}}}
---

# GitHub & Git

Complete git version control and GitHub CLI operations.

## Quick Start

```bash
# Check repository status
git status

# View recent commits
git log --oneline -10

# Create a branch, make changes, and push
git checkout -b feature/my-feature
git add -A
git commit -m "Add my feature"
git push -u origin feature/my-feature
```

## Git Commands

| Command | Description | Destructive? |
|---------|-------------|--------------|
| `git status` | Working tree status | No |
| `git log --oneline -N` | Recent N commits | No |
| `git diff` | Unstaged changes | No |
| `git diff --staged` | Staged changes | No |
| `git branch -a` | List all branches | No |
| `git add FILES` | Stage files | Yes |
| `git commit -m "MSG"` | Create commit | Yes |
| `git push origin BRANCH` | Push to remote | Yes |
| `git pull origin BRANCH` | Pull from remote | Yes |
| `git checkout BRANCH` | Switch branches | Yes |
| `git stash push -m "MSG"` | Stash changes | Yes |
| `git stash pop` | Restore stashed changes | Yes |
| `git reset --mixed HEAD~1` | Undo last commit (keep changes) | Yes |
| `git tag -a v1.0 -m "MSG"` | Create annotated tag | Yes |

## GitHub CLI Commands

| Command | Description |
|---------|-------------|
| `gh pr list` | List open pull requests |
| `gh pr create --title "T" --body "B"` | Create PR |
| `gh pr view NUMBER` | View PR details |
| `gh pr checks NUMBER` | View CI status |
| `gh issue list` | List open issues |
| `gh issue create --title "T" --body "B"` | Create issue |
| `gh release list` | List releases |

## Examples

### Create a PR

```bash
git checkout -b feature/new-feature
# ... make changes ...
git add -A
git commit -m "Add new feature"
git push -u origin feature/new-feature
gh pr create --title "Add new feature" --body "Description of changes"
```

### Amend Last Commit

```bash
git add -A
git commit --amend --no-edit
```

## Tips

- Always check `git status` before committing
- Use `git diff --staged` to review what will be committed
- Never force-push to main/master without explicit user approval
- Use `git log --oneline --graph --all` for a visual branch view
- When resolving conflicts: edit files, then `git add` the resolved files
```

#### Example 3: Skill with Parameters and Environment (web-search)

```yaml
---
name: web-search
description: "Search the web using Google Custom Search API. Use when the user needs current information, news, documentation, or any web-based lookup that requires up-to-date results."
version: "1.0.0"
tags: ["search", "web", "google"]
metadata: {"echomind":{"emoji":"🔍","category":"search","approval":"never_require","timeout":15,"output_limit":32768,"requires":{"env":["GOOGLE_SEARCH_API_KEY","GOOGLE_SEARCH_CX"]}}}
---

# Web Search

Search the web via Google Custom Search API. API keys are managed by the MCP gateway -- you never need to provide them.

## Quick Start

```bash
# Basic search
curl -s "https://www.googleapis.com/customsearch/v1?key=${GOOGLE_SEARCH_API_KEY}&cx=${GOOGLE_SEARCH_CX}&q=python+async+patterns" | jq '.items[:5] | .[] | {title, link, snippet}'

# Search with result count
curl -s "https://www.googleapis.com/customsearch/v1?key=${GOOGLE_SEARCH_API_KEY}&cx=${GOOGLE_SEARCH_CX}&q=fastapi+websocket&num=3" | jq '.items[] | {title, link, snippet}'
```

## Tips

- Always pipe through `jq` to extract relevant fields
- Use `+` to join query terms in the URL
- Limit results with `&num=N` (max 10 per request)
- The API key and CX are injected automatically by the MCP gateway
- Do NOT hardcode or echo API keys in any command
```

---

## 12. Skills Engine Implementation Plan

This section provides the file-by-file implementation plan for the skills engine that lives inside the MCP gateway service.

### 12.1 Skills Directory Structure

```
src/mcp_gateway/
  skills/
    __init__.py
    parser.py             # SKILL.md frontmatter + body parser
    registry.py           # SkillRegistry: discovery, caching, listing
    executor.py           # SkillExecutor: subprocess execution with limits
    exceptions.py         # Domain exceptions
```

### 12.2 `src/mcp_gateway/skills/exceptions.py` -- Domain Exceptions

```python
"""
Domain exceptions for the skills engine.

All exceptions are specific to skill operations and are caught
by the MCP error handler middleware to produce proper MCP error responses.
"""


class SkillError(Exception):
    """Base exception for all skill-related errors."""


class SkillNotFoundError(SkillError):
    """Raised when a requested skill does not exist in the registry."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillParseError(SkillError):
    """Raised when a SKILL.md file cannot be parsed."""

    def __init__(self, skill_name: str, reason: str) -> None:
        self.skill_name = skill_name
        self.reason = reason
        super().__init__(f"Failed to parse skill '{skill_name}': {reason}")


class SkillTimeoutError(SkillError):
    """Raised when skill execution exceeds the timeout limit."""

    def __init__(
        self, skill_name: str, timeout_seconds: int, elapsed_ms: int
    ) -> None:
        self.skill_name = skill_name
        self.timeout_seconds = timeout_seconds
        self.elapsed_ms = elapsed_ms
        super().__init__(
            f"Skill '{skill_name}' timed out after {timeout_seconds}s "
            f"(elapsed: {elapsed_ms}ms)"
        )


class SkillExecutionError(SkillError):
    """Raised when skill execution fails for non-timeout reasons."""

    def __init__(self, skill_name: str, reason: str) -> None:
        self.skill_name = skill_name
        self.reason = reason
        super().__init__(f"Skill '{skill_name}' execution failed: {reason}")
```

### 12.3 `src/mcp_gateway/skills/parser.py` -- SKILL.md Parser

Responsible for parsing YAML frontmatter and markdown body from SKILL.md files. Uses `python-frontmatter` for robust parsing with fallback to manual `---` splitting.

```python
"""
SKILL.md parser for the skills engine.

Parses YAML frontmatter and markdown body from SKILL.md files.
Validates required fields and normalizes metadata.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

from .exceptions import SkillParseError

logger = logging.getLogger(__name__)

# Validation constants
_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_MAX_NAME_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 1024
_VALID_CATEGORIES = {
    "developer", "search", "media", "system", "communication", "general",
}
_VALID_APPROVAL_MODES = {"always_require", "never_require"}
_VALID_OS_VALUES = {"linux", "darwin"}


@dataclass(frozen=True)
class SkillRequirements:
    """Binary and environment requirements for a skill."""

    bins: tuple[str, ...] = ()
    any_bins: tuple[str, ...] = ()
    env: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillMetadata:
    """Parsed EchoMind metadata from the frontmatter metadata field."""

    emoji: str = "🔧"
    category: str = "general"
    approval: str = "never_require"
    timeout: int = 30
    output_limit: int = 65_536
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    os: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedSkill:
    """
    Complete parsed SKILL.md representation.

    Attributes:
        name: Unique skill identifier (matches directory name).
        description: What the skill does and when to trigger it.
        version: Semantic version string.
        author: Skill author (optional).
        homepage: Reference URL (optional).
        license: License identifier (optional).
        tags: Category tags for filtering.
        metadata: EchoMind-specific configuration.
        body: Markdown instruction body (loaded on demand).
        skill_dir: Absolute path to the skill directory.
    """

    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    homepage: str | None = None
    license: str | None = None
    tags: tuple[str, ...] = ()
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    body: str = ""
    skill_dir: Path = field(default_factory=lambda: Path("."))


def parse_skill_md(skill_dir: Path) -> ParsedSkill:
    """
    Parse a SKILL.md file from a skill directory.

    Args:
        skill_dir: Path to the skill directory containing SKILL.md.

    Returns:
        Fully parsed and validated ParsedSkill.

    Raises:
        SkillParseError: If the file is missing, malformed, or fails validation.
    """
    skill_name = skill_dir.name
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        raise SkillParseError(skill_name, "SKILL.md file not found")

    try:
        raw_content = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        raise SkillParseError(skill_name, f"Cannot read file: {e}") from e

    try:
        post = frontmatter.loads(raw_content)
    except Exception as e:
        raise SkillParseError(
            skill_name, f"Invalid YAML frontmatter: {e}"
        ) from e

    fm: dict[str, Any] = dict(post.metadata)
    body: str = post.content.strip()

    # Validate required fields
    name = fm.get("name")
    if not name:
        raise SkillParseError(skill_name, "Missing required field: name")

    if not isinstance(name, str) or not _NAME_PATTERN.match(name):
        raise SkillParseError(
            skill_name,
            f"Invalid name '{name}': must be lowercase alphanumeric "
            f"with hyphens, no leading/trailing/consecutive hyphens",
        )

    if len(name) > _MAX_NAME_LENGTH:
        raise SkillParseError(
            skill_name, f"Name exceeds {_MAX_NAME_LENGTH} characters"
        )

    if name != skill_name:
        raise SkillParseError(
            skill_name,
            f"Name '{name}' does not match directory name '{skill_name}'",
        )

    description = fm.get("description")
    if not description:
        raise SkillParseError(
            skill_name, "Missing required field: description"
        )

    if len(description) > _MAX_DESCRIPTION_LENGTH:
        raise SkillParseError(
            skill_name,
            f"Description exceeds {_MAX_DESCRIPTION_LENGTH} characters",
        )

    # Parse optional fields
    tags = tuple(fm.get("tags", []))
    em_metadata = _parse_echomind_metadata(skill_name, fm.get("metadata"))

    return ParsedSkill(
        name=name,
        description=description,
        version=str(fm.get("version", "1.0.0")),
        author=fm.get("author"),
        homepage=fm.get("homepage"),
        license=fm.get("license"),
        tags=tags,
        metadata=em_metadata,
        body=body,
        skill_dir=skill_dir.resolve(),
    )


def _parse_echomind_metadata(
    skill_name: str, raw: Any
) -> SkillMetadata:
    """
    Parse the echomind metadata sub-object.

    Args:
        skill_name: Skill name for error context.
        raw: Raw metadata value (string JSON, dict, or None).

    Returns:
        Parsed SkillMetadata.
    """
    if raw is None:
        return SkillMetadata()

    # Handle string JSON (single-line frontmatter)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                f"⚠️ Skill '{skill_name}': invalid metadata JSON: {e}"
            )
            return SkillMetadata()

    if not isinstance(raw, dict):
        return SkillMetadata()

    em = raw.get("echomind", {})
    if not isinstance(em, dict):
        return SkillMetadata()

    # Parse requires sub-object
    req_raw = em.get("requires", {})
    requires = SkillRequirements(
        bins=tuple(req_raw.get("bins", [])),
        any_bins=tuple(req_raw.get("any_bins", [])),
        env=tuple(req_raw.get("env", [])),
    )

    # Validate category
    category = em.get("category", "general")
    if category not in _VALID_CATEGORIES:
        logger.warning(
            f"⚠️ Skill '{skill_name}': invalid category '{category}', "
            f"using 'general'"
        )
        category = "general"

    # Validate approval
    approval = em.get("approval", "never_require")
    if approval not in _VALID_APPROVAL_MODES:
        logger.warning(
            f"⚠️ Skill '{skill_name}': invalid approval '{approval}', "
            f"using 'never_require'"
        )
        approval = "never_require"

    # Validate os
    os_values = tuple(em.get("os", []))
    for os_val in os_values:
        if os_val not in _VALID_OS_VALUES:
            logger.warning(
                f"⚠️ Skill '{skill_name}': invalid os value '{os_val}'"
            )

    return SkillMetadata(
        emoji=em.get("emoji", "🔧"),
        category=category,
        approval=approval,
        timeout=int(em.get("timeout", 30)),
        output_limit=int(em.get("output_limit", 65_536)),
        requires=requires,
        os=os_values,
    )
```

### 12.4 `src/mcp_gateway/skills/registry.py` -- SkillRegistry

```python
"""
Skill registry for the MCP gateway.

Discovers, loads, and caches SKILL.md files from the skills directory.
Provides listing, lookup, and hot-reload capabilities.
"""

import logging
import platform
import shutil
from pathlib import Path

from .exceptions import SkillNotFoundError
from .parser import ParsedSkill, SkillMetadata, parse_skill_md

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Registry that discovers and manages SKILL.md files.

    Scans a skills directory at startup, parses all SKILL.md files,
    and provides lookup/listing methods for the MCP tools layer.

    Attributes:
        skills_dir: Path to the skills directory.
    """

    def __init__(self, skills_dir: Path) -> None:
        """
        Initialize the registry.

        Args:
            skills_dir: Path to the directory containing skill subdirectories.
        """
        self._skills_dir = skills_dir
        self._skills: dict[str, ParsedSkill] = {}
        self._load_errors: dict[str, str] = {}

    async def discover(self) -> None:
        """
        Scan the skills directory and parse all SKILL.md files.

        Errors for individual skills are logged but do not prevent
        other skills from loading.
        """
        self._skills.clear()
        self._load_errors.clear()

        if not self._skills_dir.exists():
            logger.warning(
                f"⚠️ Skills directory not found: {self._skills_dir}"
            )
            return

        if not self._skills_dir.is_dir():
            logger.error(
                f"❌ Skills path is not a directory: {self._skills_dir}"
            )
            return

        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue

            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                skill = parse_skill_md(entry)

                # Check platform eligibility
                if not self._check_platform(skill):
                    logger.info(
                        f"⏭️ Skipping skill '{skill.name}': "
                        f"not eligible for platform '{platform.system().lower()}'"
                    )
                    continue

                # Check binary requirements
                if not self._check_binaries(skill):
                    logger.info(
                        f"⏭️ Skipping skill '{skill.name}': "
                        f"missing required binaries"
                    )
                    continue

                self._skills[skill.name] = skill
                logger.info(
                    f"{skill.metadata.emoji} Loaded skill: {skill.name} "
                    f"({skill.description[:60]}...)"
                )

            except Exception as e:
                self._load_errors[entry.name] = str(e)
                logger.warning(f"⚠️ Failed to load skill '{entry.name}': {e}")

        logger.info(
            f"🔧 SkillRegistry: {len(self._skills)} skills loaded, "
            f"{len(self._load_errors)} errors"
        )

    def list_skills(self) -> list[ParsedSkill]:
        """
        List all loaded skills.

        Returns:
            List of all eligible, successfully parsed skills.
        """
        return list(self._skills.values())

    def get_skill(self, name: str) -> ParsedSkill:
        """
        Get a skill by name.

        Args:
            name: Skill identifier.

        Returns:
            The parsed skill.

        Raises:
            SkillNotFoundError: If the skill does not exist.
        """
        skill = self._skills.get(name)
        if skill is None:
            raise SkillNotFoundError(name)
        return skill

    def has_skill(self, name: str) -> bool:
        """
        Check if a skill exists in the registry.

        Args:
            name: Skill identifier.

        Returns:
            True if the skill is loaded.
        """
        return name in self._skills

    def count(self) -> int:
        """
        Get the number of loaded skills.

        Returns:
            Number of loaded skills.
        """
        return len(self._skills)

    async def reload(self) -> None:
        """
        Re-scan the skills directory and reload all skills.

        Used for hot-reload when SKILL.md files change on disk.
        """
        logger.info("🔄 Reloading skills registry...")
        await self.discover()

    def _check_platform(self, skill: ParsedSkill) -> bool:
        """
        Check if the skill is eligible for the current platform.

        Args:
            skill: Parsed skill to check.

        Returns:
            True if the skill has no OS restriction or matches the current OS.
        """
        if not skill.metadata.os:
            return True
        current_os = platform.system().lower()
        return current_os in skill.metadata.os

    def _check_binaries(self, skill: ParsedSkill) -> bool:
        """
        Check if required binaries are available on PATH.

        Args:
            skill: Parsed skill to check.

        Returns:
            True if all required binaries are satisfied.
        """
        reqs = skill.metadata.requires

        # All bins must be present
        for binary in reqs.bins:
            if shutil.which(binary) is None:
                logger.debug(
                    f"Missing required binary '{binary}' for skill "
                    f"'{skill.name}'"
                )
                return False

        # At least one of any_bins must be present
        if reqs.any_bins:
            if not any(shutil.which(b) is not None for b in reqs.any_bins):
                logger.debug(
                    f"None of {reqs.any_bins} found for skill '{skill.name}'"
                )
                return False

        return True
```

### 12.5 `src/mcp_gateway/skills/executor.py` -- SkillExecutor

```python
"""
Skill executor for the MCP gateway.

Executes bash commands in a subprocess with timeout enforcement,
output size limits, and environment isolation.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from .exceptions import SkillExecutionError, SkillTimeoutError

logger = logging.getLogger(__name__)

# Hard ceiling for any execution, regardless of trust level
_ABSOLUTE_MAX_TIMEOUT = 300
_ABSOLUTE_MAX_OUTPUT = 1_048_576  # 1 MB


@dataclass(frozen=True)
class ExecutionResult:
    """
    Result of a skill execution.

    Attributes:
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        exit_code: Process exit code (0 = success).
        truncated: Whether output was truncated due to size limit.
        duration_ms: Execution duration in milliseconds.
    """

    stdout: str
    stderr: str
    exit_code: int
    truncated: bool
    duration_ms: int


class SkillExecutor:
    """
    Executes skill commands in isolated subprocesses.

    Security measures:
    - Timeout enforcement via asyncio.wait_for
    - Output size limits to prevent OOM
    - Environment isolation (clean env + skill-specific vars only)
    - No shell=True (commands passed as argument list to /bin/bash -c)
    - Process killed on timeout (SIGKILL)

    Attributes:
        default_timeout: Default timeout in seconds.
        default_output_limit: Default max output bytes.
    """

    def __init__(
        self,
        default_timeout: int = 30,
        default_output_limit: int = 65_536,
    ) -> None:
        """
        Initialize the executor.

        Args:
            default_timeout: Default timeout in seconds (max 300).
            default_output_limit: Default max output in bytes (max 1 MB).
        """
        self.default_timeout = min(default_timeout, _ABSOLUTE_MAX_TIMEOUT)
        self.default_output_limit = min(
            default_output_limit, _ABSOLUTE_MAX_OUTPUT
        )

    async def execute(
        self,
        command: str,
        *,
        skill_name: str = "unknown",
        timeout: int | None = None,
        output_limit: int | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a bash command in an isolated subprocess.

        The command is executed via ``/bin/bash -c <command>`` to ensure
        consistent shell behavior. Environment is built from a minimal
        base (PATH, HOME, LANG) plus any skill-specific variables.

        Args:
            command: Bash command string to execute.
            skill_name: Skill name for logging context.
            timeout: Timeout in seconds (overrides default).
            output_limit: Max output bytes (overrides default).
            env: Additional environment variables for the subprocess.
            cwd: Working directory for the subprocess.

        Returns:
            ExecutionResult with stdout, stderr, exit code, and metadata.

        Raises:
            SkillTimeoutError: If command exceeds timeout.
            SkillExecutionError: If command cannot be started.
        """
        effective_timeout = min(
            timeout or self.default_timeout, _ABSOLUTE_MAX_TIMEOUT
        )
        effective_output_limit = min(
            output_limit or self.default_output_limit, _ABSOLUTE_MAX_OUTPUT
        )

        if not command or not command.strip():
            raise SkillExecutionError(skill_name, "Command cannot be empty")

        # Build isolated environment
        process_env = self._build_env(env)

        start_time = time.monotonic()
        proc: asyncio.subprocess.Process | None = None

        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash", "-c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                cwd=cwd,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Apply output limits
            truncated = False
            if len(stdout_bytes) > effective_output_limit:
                stdout_bytes = stdout_bytes[:effective_output_limit]
                truncated = True
            if len(stderr_bytes) > effective_output_limit:
                stderr_bytes = stderr_bytes[:effective_output_limit]
                truncated = True

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            exit_code = proc.returncode if proc.returncode is not None else -1

            logger.info(
                f"🔧 Skill '{skill_name}' completed: "
                f"exit_code={exit_code}, "
                f"duration={duration_ms}ms, "
                f"stdout={len(stdout_bytes)}B, "
                f"stderr={len(stderr_bytes)}B"
                f"{', truncated' if truncated else ''}"
            )

            return ExecutionResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                truncated=truncated,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)

            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass

            logger.warning(
                f"⏰ Skill '{skill_name}' timed out after "
                f"{effective_timeout}s (elapsed: {duration_ms}ms)"
            )
            raise SkillTimeoutError(
                skill_name, effective_timeout, duration_ms
            )

        except OSError as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                f"❌ Skill '{skill_name}' execution error: {e}"
            )
            raise SkillExecutionError(skill_name, str(e)) from e

    def _build_env(
        self, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        """
        Build an isolated environment for subprocess execution.

        Starts with a minimal set of safe environment variables
        (PATH, HOME, LANG, TERM) and adds any skill-specific vars.

        Args:
            extra: Additional environment variables.

        Returns:
            Environment dict for subprocess.
        """
        base_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "TERM": "xterm-256color",
        }

        if extra:
            base_env.update(extra)

        return base_env
```

---

## 13. MCP Tool Registration

This section describes how skills are exposed as MCP tools in the gateway's `main.py` and `tools/skills.py`.

### 13.1 Tool Definitions (`src/mcp_gateway/tools/skills.py`)

Three MCP tools provide the progressive disclosure flow:

```python
"""
Skills MCP tools for the gateway.

Exposes skill listing, info retrieval, and execution as MCP tools.
Follows the progressive disclosure pattern:
  1. skills_list() -- agent sees what is available
  2. skills_get_info(name) -- agent reads instructions
  3. skills_execute(name, command) -- agent runs a command
"""

import logging
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..skills.executor import ExecutionResult, SkillExecutor
from ..skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillSummary(BaseModel):
    """Summary of a skill returned by skills_list."""

    name: str = Field(..., description="Skill identifier")
    description: str = Field(..., description="What the skill does")
    emoji: str = Field("🔧", description="Display emoji")
    category: str = Field("general", description="Skill category")
    tags: list[str] = Field(default_factory=list, description="Tags")
    requires_approval: bool = Field(
        False, description="Whether execution requires user approval"
    )


class SkillDetail(BaseModel):
    """Full skill detail returned by skills_get_info."""

    name: str
    description: str
    version: str
    author: str | None = None
    homepage: str | None = None
    tags: list[str] = Field(default_factory=list)
    emoji: str = "🔧"
    category: str = "general"
    timeout: int = 30
    requires_approval: bool = False
    body: str = Field(..., description="Markdown instructions")


class SkillExecuteResult(BaseModel):
    """Result of skill execution."""

    success: bool
    output: str
    exit_code: int
    duration_ms: int
    truncated: bool = False


def register_skills_tools(
    mcp: FastMCP,
    registry: SkillRegistry,
    executor: SkillExecutor,
) -> None:
    """
    Register skill MCP tools on the FastMCP server.

    Args:
        mcp: FastMCP server instance.
        registry: Loaded skill registry.
        executor: Configured skill executor.
    """

    @mcp.tool
    async def skills_list() -> list[SkillSummary]:
        """
        List all available skills with name, description, and metadata.

        The agent reads this list to decide which skill is relevant
        for the user's request. Call skills_get_info(name) to load
        full instructions before executing.
        """
        skills = registry.list_skills()
        return [
            SkillSummary(
                name=s.name,
                description=s.description,
                emoji=s.metadata.emoji,
                category=s.metadata.category,
                tags=list(s.tags),
                requires_approval=s.metadata.approval == "always_require",
            )
            for s in skills
        ]

    @mcp.tool
    async def skills_get_info(skill_name: str) -> SkillDetail:
        """
        Get detailed information and instructions for a specific skill.

        Returns the full SKILL.md body with bash examples and workflows.
        Call this before executing to learn the correct commands.

        Args:
            skill_name: The skill identifier from skills_list().
        """
        skill = registry.get_skill(skill_name)
        return SkillDetail(
            name=skill.name,
            description=skill.description,
            version=skill.version,
            author=skill.author,
            homepage=skill.homepage,
            tags=list(skill.tags),
            emoji=skill.metadata.emoji,
            category=skill.metadata.category,
            timeout=skill.metadata.timeout,
            requires_approval=skill.metadata.approval == "always_require",
            body=skill.body,
        )

    @mcp.tool
    async def skills_execute(
        skill_name: str,
        command: str,
        timeout: int | None = None,
    ) -> SkillExecuteResult:
        """
        Execute a bash command in the context of a skill.

        The command runs in an isolated subprocess with timeout
        and output size limits. Use skills_get_info first to learn
        the correct bash patterns for this skill.

        Args:
            skill_name: The skill to execute under.
            command: Bash command string to run.
            timeout: Optional timeout override in seconds.
        """
        skill = registry.get_skill(skill_name)

        effective_timeout = timeout or skill.metadata.timeout
        env_vars: dict[str, str] = {}

        # Inject required env vars from the gateway's API key manager
        # (handled by the MCP gateway layer, not shown here)

        result: ExecutionResult = await executor.execute(
            command=command,
            skill_name=skill_name,
            timeout=effective_timeout,
            output_limit=skill.metadata.output_limit,
            env=env_vars,
        )

        return SkillExecuteResult(
            success=result.exit_code == 0,
            output=result.stdout if result.stdout else result.stderr,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            truncated=result.truncated,
        )

    logger.info(
        f"🔧 Registered skills tools: skills_list, skills_get_info, "
        f"skills_execute ({registry.count()} skills available)"
    )
```

### 13.2 Registration in `main.py`

```python
# In src/mcp_gateway/main.py (relevant excerpt)

from fastmcp import FastMCP
from .config import GatewayConfig
from .skills.registry import SkillRegistry
from .skills.executor import SkillExecutor
from .tools.skills import register_skills_tools

config = GatewayConfig()

mcp = FastMCP("EchoMind Gateway")

# Initialize skills engine
skill_registry = SkillRegistry(skills_dir=Path(config.skills_dir))
skill_executor = SkillExecutor(
    default_timeout=config.skill_default_timeout,
    default_output_limit=config.skill_default_output_limit,
)

# Discover skills on startup
await skill_registry.discover()

# Register MCP tools
register_skills_tools(mcp, skill_registry, skill_executor)

# Register other tool namespaces (search, connectors, api)...
```

---

## 14. Migration Plan: 30 Tools to Skills

### 14.1 Migration Priority Order

Migration is ordered by: (1) how many native tools the skill replaces, (2) usage frequency, and (3) complexity.

| Wave | Priority | Skill to Create | Native Tools Replaced | Count | Effort |
|------|----------|-----------------|----------------------|-------|--------|
| **Wave 1** | P0 | System prompt (bash patterns) | read, write, grep, glob, list_dir, tree, mkdir, move, delete, http_request, env_get, which, diff, patch, find_replace | 15 | Medium |
| **Wave 1** | P0 | `github` | git_log, git_diff, git_status, git_add, git_commit, git_branch, git_checkout, git_stash, git_push, git_pull, git_reset, git_clone, git_tag | 13 | Medium |
| **Wave 1** | P1 | `file-edit` | edit, find_replace | 2 | Low |
| **Wave 2** | P1 | `weather` | (none -- new capability, used as test) | 0 | Low |
| **Wave 2** | P1 | `web-search` | http_request (partially) | 0 | Low |
| **Wave 2** | P2 | `coding-agent` | (none -- new capability) | 0 | Medium |
| **Wave 2** | P2 | `summarize` | (none -- new capability) | 0 | Low |

### 14.2 Per-Tool Migration Details

#### Wave 1 -- Core Tools (execute during Phase 3 / Week 5)

**System Prompt (replaces 15 tools)**

The system prompt teaches the agent bash patterns for operations previously handled by native tools. No SKILL.md file needed -- these patterns go directly into the agent's `instructions` field in `config.yaml`.

Bash patterns to teach:
```
read       -> cat -n FILE | head -n LIMIT
write      -> cat > FILE << 'EOF' ... EOF
grep       -> rg PATTERN PATH --glob '*.py' --line-number
glob       -> find . -name '*.py' -type f | head -100
list_dir   -> ls -la PATH
tree       -> tree -L 3 PATH
mkdir      -> mkdir -p PATH
move       -> mv SOURCE DEST
delete     -> rm -rf PATH (ALWAYS confirm with user first)
http       -> curl -s URL | jq '.'
env_get    -> echo $VAR_NAME
which      -> which COMMAND
diff       -> diff -u FILE_A FILE_B
patch      -> patch < DIFF_FILE
find_replace -> rg PATTERN -l | xargs sed -i 's/OLD/NEW/g'
```

**`github` skill (replaces 13 git tools)**

- File: `config/skills/github/SKILL.md`
- Content: See example in section 11.4 above
- Native code to delete: `src/agent/tools/git.py`, `src/agent/tools/git_extended.py`
- Test: `git status` via `skills_execute("github", "git status")` returns clean output

**`file-edit` skill (replaces edit + find_replace)**

- File: `config/skills/file-edit/SKILL.md`
- Teaches: `sed -i`, `awk`, `perl -pi -e` patterns for structured editing
- Native code to delete: None (keep `edit.py` as optional native alongside skill)
- Test: Multi-line replacement via sed heredoc pattern

#### Wave 2 -- Extended Skills

**`weather` skill**

- File: `config/skills/weather/SKILL.md`
- Content: See example in section 11.4 above
- Native code to delete: None (new capability)
- Test: `curl -s "wttr.in/Zurich?format=3"` returns temperature

**`web-search` skill**

- File: `config/skills/web-search/SKILL.md`
- Content: See example in section 11.4 above
- Native code to delete: `src/agent/tools/web.py`
- Test: Google search API call returns JSON results

**`coding-agent` skill**

- File: `config/skills/coding-agent/SKILL.md`
- Teaches: Running Claude Code, Codex, or other coding agents via CLI
- Test: `claude --help` returns usage info

**`summarize` skill**

- File: `config/skills/summarize/SKILL.md`
- Teaches: URL and video summarization via `yt-dlp` + LLM
- Test: `curl -s URL | head -100` fetches page content

### 14.3 Native Code Deletion Schedule

| File | Deleted In | Tools Removed | Lines |
|------|-----------|---------------|-------|
| `src/agent/tools/git.py` | Wave 1 | git_log, git_diff, git_status, git_add, git_commit | ~300 |
| `src/agent/tools/git_extended.py` | Wave 1 | git_branch..git_tag | ~400 |
| `src/agent/tools/filesystem.py` | Wave 1 | read, write, grep, glob | ~260 |
| `src/agent/tools/directory.py` | Wave 1 | list_dir, tree, mkdir, move, delete | ~200 |
| `src/agent/tools/system.py` | Wave 1 | env_get, which, find_replace | ~120 |
| `src/agent/tools/text.py` | Wave 1 | diff, patch | ~100 |
| `src/agent/tools/web.py` | Wave 2 | http_request | ~80 |
| **Total** | | **29 tools** | **~1,460 LOC** |

**Kept files:**
- `src/agent/tools/edit.py` -- Optional native tool (safer than sed for structured edits)
- `src/agent/tools/execution.py` -- Bash core tool (enhanced with sandbox)
- `src/agent/tools/registry.py` -- Simplified to register only edit + bash
- `src/agent/tools/middleware.py` -- Reused for approval/path middleware

### 14.4 Registry Simplification

After migration, `src/agent/tools/registry.py` shrinks from 30 tool registrations to 2:

```python
def _register_core_tools(self) -> None:
    """Register minimal native tools (post-migration)."""
    # Bash is the primary tool -- skills teach it what to do
    self.register("bash", create_bash_tool(), approval_mode="always_require")

    # Edit kept as optional native for structured file editing
    self.register("edit", create_edit_tool(), approval_mode="always_require")
```

---

## 15. Skills Directory Structure

```
config/skills/
  github/
    SKILL.md                # Git + GitHub CLI patterns
  file-edit/
    SKILL.md                # Structured file editing (sed, awk, perl)
  weather/
    SKILL.md                # Weather via wttr.in
  web-search/
    SKILL.md                # Google Custom Search
  coding-agent/
    SKILL.md                # Sub-agent orchestration
  summarize/
    SKILL.md                # URL/video summarization
  tmux/
    SKILL.md                # tmux session management (copied from Moltbot)
  nano-pdf/
    SKILL.md                # PDF operations (copied from Moltbot)
  1password/
    SKILL.md                # Secrets management via op CLI
  obsidian/
    SKILL.md                # Obsidian vault operations
  openai-whisper/
    SKILL.md                # Audio transcription
  openai-image-gen/
    SKILL.md                # Image generation
  echomind-search/
    SKILL.md                # EchoMind RAG search patterns
  echomind-documents/
    SKILL.md                # EchoMind document management
  echomind-connectors/
    SKILL.md                # EchoMind connector management
```

This directory is mounted into the MCP gateway container as a read-only volume:

```yaml
# docker-compose.yml
services:
  echomind-mcp:
    volumes:
      - ./config/skills:/app/skills:ro
```

---

## 16. Security Considerations

### 16.1 Command Injection Prevention

Skills execute commands via `subprocess` with these safeguards:

| Measure | Implementation | Reference |
|---------|---------------|-----------|
| No `shell=True` on subprocess | Commands run via `/bin/bash -c <cmd>` as argument list, not via `shell=True` kwarg | [Snyk -- Command Injection Prevention](https://snyk.io/blog/command-injection-python-prevention-examples/) |
| Environment isolation | Subprocess gets a minimal env (PATH, HOME, LANG, TERM) plus only skill-declared vars | [Secure Coding Practices](https://securecodingpractices.com/prevent-command-injection-python-subprocess/) |
| No user input in command construction | The agent constructs the command; the executor runs it verbatim. The MCP gateway never interpolates user input into commands. | [Semgrep -- Command Injection in Python](https://semgrep.dev/docs/cheat-sheets/python-command-injection) |
| Sandbox boundary | In production, the MCP gateway runs OUTSIDE the sandbox. Bash execution happens inside the sandbox container, which has no access to PG/Qdrant/MinIO. | See `agent_sandbox-containers.md` |

### 16.2 Output Size Limits

Prevent OOM from commands that produce unbounded output (e.g., `cat /dev/urandom`, `find /`):

- **Default limit**: 64 KB per execution (`output_limit` in SkillMetadata)
- **Maximum limit**: 1 MB (hard ceiling in `SkillExecutor._ABSOLUTE_MAX_OUTPUT`)
- **Truncation**: Output is truncated at the byte level with a `truncated=True` flag in the result
- **Agent guidance**: Skills teach output filtering patterns (`| head -100`, `| jq '.'`, `| wc -l`)

### 16.3 Timeout Enforcement

- **Default**: 30 seconds per skill execution
- **Per-skill override**: Set in SKILL.md metadata `timeout` field
- **Per-call override**: Agent can pass `timeout` parameter to `skills_execute`
- **Hard ceiling**: 300 seconds (`_ABSOLUTE_MAX_TIMEOUT`) -- no execution can exceed this
- **Enforcement**: `asyncio.wait_for` with `proc.kill()` on timeout
- **Process cleanup**: After `kill()`, executor calls `await proc.wait()` to reap the zombie process

### 16.4 Environment Variable Isolation

| What the subprocess sees | What it does NOT see |
|--------------------------|---------------------|
| `PATH` (from gateway host) | Database URLs |
| `HOME` (from gateway host) | API keys (unless declared in skill's `requires.env`) |
| `LANG`, `TERM` | JWT tokens |
| Skill-declared env vars (injected by API key manager) | Other skills' env vars |

API keys for skills that declare `requires.env` are injected by the `APIKeyManager` (see `agent_mcp-gateway.md` section 7). The agent never sees raw key values -- it constructs commands using `${VAR_NAME}` references, and the gateway injects the actual values into the subprocess environment.

### 16.5 Dangerous Command Patterns

The MCP gateway's audit logger flags (but does not block initially) these patterns. Blocking will be added in a future security hardening phase:

| Pattern | Risk | Initial | Hardened |
|---------|------|---------|---------|
| `rm -rf /` | Filesystem destruction | Log + warn | Block |
| `git push --force` to main/master | History rewrite | Log + warn | Require approval |
| `chmod 777` | Permission escalation | Log + warn | Block |
| `curl \| bash` | Remote code execution | Log + warn | Block |
| `> /etc/` writes | System file modification | Log + warn | Block (via sandbox FS anyway) |
| `env` / `printenv` | Environment exfiltration | Log + warn | Filter sensitive vars |

---

## 17. Test Plan

### 17.1 Parser Tests (`tests/unit/mcp_gateway/skills/test_parser.py`)

| Test Case | Input | Expected |
|-----------|-------|----------|
| Valid minimal SKILL.md | name + description only | ParsedSkill with defaults |
| Valid full SKILL.md | All fields populated | ParsedSkill with all fields |
| Missing name field | No `name` in frontmatter | SkillParseError |
| Missing description field | No `description` in frontmatter | SkillParseError |
| Invalid name format | `"My Skill"` (spaces, uppercase) | SkillParseError |
| Name too long | 65-char name | SkillParseError |
| Name mismatch | name != directory name | SkillParseError |
| Invalid YAML frontmatter | Malformed YAML | SkillParseError |
| Missing frontmatter delimiters | No `---` lines | SkillParseError |
| Empty body | Frontmatter only, no markdown | ParsedSkill with empty body |
| Invalid metadata JSON | `metadata: {broken` | SkillMetadata with defaults (graceful) |
| Invalid category | `"category": "invalid"` | Falls back to `"general"`, logs warning |
| Invalid approval mode | `"approval": "maybe"` | Falls back to `"never_require"`, logs warning |
| Description with angle brackets | `<script>alert(1)</script>` | SkillParseError |
| Unicode in description | `"Suche im Web"` | ParsedSkill (valid) |

### 17.2 Registry Tests (`tests/unit/mcp_gateway/skills/test_registry.py`)

| Test Case | Setup | Expected |
|-----------|-------|----------|
| Discover from valid directory | 3 valid skill dirs | 3 skills loaded |
| Discover with mixed valid/invalid | 2 valid, 1 malformed | 2 loaded, 1 error logged |
| Discover from empty directory | No subdirectories | 0 skills, no errors |
| Discover from nonexistent path | Path does not exist | 0 skills, warning logged |
| get_skill existing | After discover | Returns ParsedSkill |
| get_skill nonexistent | Name not loaded | Raises SkillNotFoundError |
| has_skill true/false | After discover | Correct boolean |
| list_skills | After discover | Returns all loaded skills |
| reload | Modify files, call reload | Updated skills |
| Platform filtering | Skill with `os: ["darwin"]` on Linux | Skill skipped |
| Binary check pass | `requires.bins: ["bash"]` | Skill loaded |
| Binary check fail | `requires.bins: ["nonexistent-bin"]` | Skill skipped |
| any_bins check pass | `any_bins: ["nonexistent", "bash"]` | Skill loaded |
| any_bins check fail | `any_bins: ["nonexistent1", "nonexistent2"]` | Skill skipped |

### 17.3 Executor Tests (`tests/unit/mcp_gateway/skills/test_executor.py`)

| Test Case | Command | Expected |
|-----------|---------|----------|
| Successful command | `echo hello` | exit_code=0, stdout="hello\n" |
| Failed command | `exit 1` | exit_code=1 |
| Timeout | `sleep 60` with timeout=1 | SkillTimeoutError |
| Large output truncation | `seq 1 1000000` with limit=1024 | truncated=True, len(stdout) <= 1024 |
| Empty command | `""` | SkillExecutionError |
| Stderr output | `echo err >&2` | stderr="err\n" |
| Combined stdout/stderr | `echo out; echo err >&2` | Both populated |
| Environment isolation | `echo $HOME` | Returns gateway HOME, not sensitive vars |
| Custom env injection | env={"MY_VAR": "val"}, `echo $MY_VAR` | stdout="val\n" |
| Process cleanup on timeout | `sleep 60` | Process is killed and reaped |
| Non-UTF8 output | Binary output command | Decoded with errors="replace" |
| Duration tracking | Any command | duration_ms > 0 |
| Absolute max timeout | timeout=999 | Capped to 300 |
| Absolute max output | output_limit=9999999 | Capped to 1 MB |

### 17.4 MCP Tools Integration Tests (`tests/integration/mcp_gateway/test_skills_tools.py`)

| Test Case | Flow | Expected |
|-----------|------|----------|
| End-to-end list -> info -> execute | Call all 3 tools sequentially | Skills listed, info returned, command executed |
| skills_list returns all skills | Pre-load 3 skills | List of 3 SkillSummary objects |
| skills_get_info returns body | Request known skill | SkillDetail with body content |
| skills_get_info unknown skill | Request nonexistent name | SkillNotFoundError |
| skills_execute success | `echo test` via weather skill | SkillExecuteResult with success=True |
| skills_execute timeout | `sleep 60` with timeout=1 | Error response with timeout info |
| skills_execute with approval flag | Skill with approval="always_require" | requires_approval=True in list |

---

## 18. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `python-frontmatter` | `==1.1.0` | YAML frontmatter parsing from SKILL.md files |
| `pyyaml` | `>=6.0.1` | YAML parsing (dependency of python-frontmatter) |
| `fastmcp` | `>=3.0.0` | MCP server framework |
| `pydantic` | `>=2.6.0` | Data validation for MCP tool schemas |

These are added to `src/mcp_gateway/requirements.txt`. The `python-frontmatter` and `pyyaml` packages are the only new dependencies specific to the skills engine. All other dependencies (`fastmcp`, `pydantic`, `sqlalchemy`, etc.) are already required by the MCP gateway.

---

## 19. Citations and Sources

| Source | Date | Used For |
|--------|------|----------|
| [OpenClaw Skills Documentation](https://docs.openclaw.ai/tools/skills) | 2026-02 | SKILL.md format spec: frontmatter fields, metadata schema, discovery flow |
| [DeepWiki -- Moltbot Creating Skills](https://deepwiki.com/moltbot/moltbot/9.5-creating-skills) | 2026-02 | Skill directory structure, installer types, per-skill configuration |
| [DeepWiki -- Anthropic SKILL.md Spec](https://deepwiki.com/anthropics/skills/2.2-skill.md-format-specification) | 2026-02 | Anthropic standard: required/optional fields, name validation, body guidelines |
| [DeepWiki -- OpenAI SKILL.md Spec](https://deepwiki.com/openai/skills/8.1-skill.md-format-specification) | 2026-02 | OpenAI standard: name pattern, description constraints, validation rules |
| [Snyk -- Command Injection Prevention](https://snyk.io/blog/command-injection-python-prevention-examples/) | 2025 | Python subprocess security: argument lists vs shell=True, input validation |
| [Semgrep -- Command Injection in Python](https://semgrep.dev/docs/cheat-sheets/python-command-injection) | 2025 | Command injection patterns, shlex.quote, shlex.split |
| [Secure Coding Practices -- subprocess](https://securecodingpractices.com/prevent-command-injection-python-subprocess/) | 2025 | Environment isolation, absolute paths, resource limits |
| [python-frontmatter on PyPI](https://pypi.org/project/python-frontmatter/) | 2024-01 | YAML frontmatter parsing library (v1.1.0) |
| [frontmatter-format spec](https://github.com/jlevy/frontmatter-format) | 2025 | Convention for YAML metadata on any file |
| [Python Frontmatter docs](https://python-frontmatter.readthedocs.io/) | 2024 | Library API reference for frontmatter parsing |
| [VoltAgent/awesome-openclaw-skills](https://github.com/VoltAgent/awesome-moltbot-skills) | 2026-01 | Community skill examples, portability patterns |

---

## 20. Evaluation Scorecard

| # | Criterion | Score (1-10) | Justification |
|---|-----------|-------------|---------------|
| 1 | **Format Compatibility** | 9/10 | EchoMind SKILL.md is a superset of Anthropic/OpenAI/Moltbot formats. Existing community skills work with zero or minimal changes. |
| 2 | **Security Model** | 7/10 | Environment isolation, timeout enforcement, output limits provide good baseline. Full command analysis and blocking to be added in a future hardening phase. |
| 3 | **Developer Experience** | 9/10 | Adding a new skill = create a directory + write markdown. No Python code, no compilation, no redeployment (hot reload). |
| 4 | **Test Coverage** | 8/10 | 40+ test cases across parser, registry, executor, and integration. Edge cases (malformed files, timeouts, large output) covered. |
| 5 | **Performance** | 8/10 | Subprocess overhead ~5-10ms. Skill registry loads once at startup. No per-request disk I/O. Hot reload only when triggered. |
| 6 | **Maintainability** | 9/10 | Skills engine is ~400 LOC across 4 files. Dataclasses over classes. No ORM, no framework magic. Easy to understand and modify. |
| 7 | **Migration Risk** | 7/10 | 73% of native tools are trivial shell wrappers. The `edit` tool stays native as fallback. Rollback = re-register native tools in registry. |
