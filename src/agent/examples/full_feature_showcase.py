"""
Full Feature Showcase — Demonstrates ALL agent system capabilities (Phases 1-5).

Exercises every major subsystem without requiring a live LLM API key:
  Phase 1: Config loading, YAML parsing, env var expansion
  Phase 2: 9-layer policy engine, profile presets, provider detection
  Phase 3: 5-tier routing, intent fallback, session key generation
  Phase 4: JSONL session persistence, history provider
  Phase 5: 30 tools, approval gates, path restriction middleware

Usage (run from project root):
    cd /Users/gp/Developer/echo-mind
    PYTHONPATH=src python -m agent.examples.full_feature_showcase
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Add src/ to path so 'agent' resolves as a package
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Suppress logger output — we want clean demo output only
logging.disable(logging.CRITICAL)

from agent_framework import FunctionInvocationContext, FunctionTool

from agent.config.parser import ConfigParser
from agent.config.schema import (
    AgentConfig,
    MoltbotConfig,
    PathRestrictionConfig,
    RouteBindingConfig,
    RoutingConfig,
    SandboxConfig,
    SessionConfig,
    ToolApprovalConfig,
    ToolPolicy,
)
from agent.policy.engine import PolicyContext, ToolPolicyEngine
from agent.policy.profiles import PROFILES
from agent.policy.providers import detect_provider
from agent.routing.models import ResolvedRoute, RouteContext, RoutePeer
from agent.routing.router import AgentRouter
from agent.sessions.manager import SessionManager
from agent.tools.middleware import PathRestrictionMiddleware
from agent.tools.registry import ToolsRegistry

# === Formatting helpers ====================================================


def header(title: str) -> None:
    """Print a section header."""
    w = 70
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")


def sub(title: str) -> None:
    """Print a subsection header."""
    print(f"\n  --- {title} ---")


def ok(msg: str) -> None:
    """Print a success message."""
    print(f"    [OK] {msg}")


def info(msg: str) -> None:
    """Print an info line."""
    print(f"    {msg}")


# === Helper: build a full config programmatically ==========================


def build_config() -> MoltbotConfig:
    """
    Build a comprehensive MoltbotConfig covering all schema features.

    Returns:
        Fully populated MoltbotConfig for testing.
    """
    return MoltbotConfig(
        agents=[
            AgentConfig(
                id="assistant",
                name="EchoMind Assistant",
                model="gpt-4o-mini",
                instructions="You are a helpful assistant.",
                tools=ToolPolicy(profile="full", allow=["*"], deny=[]),
                dm_scope="per-peer",
            ),
            AgentConfig(
                id="coder",
                name="Coding Agent",
                model="gpt-4o-mini",
                instructions="You write clean code.",
                tools=ToolPolicy(
                    profile="coding",
                    allow=["read*", "write*", "grep*", "glob*", "bash", "git_*", "edit", "diff", "patch"],
                    deny=[],
                    by_provider={
                        "anthropic": ToolPolicy(deny=["bash"]),
                    },
                ),
                dm_scope="per-peer",
            ),
            AgentConfig(
                id="researcher",
                name="Research Agent",
                model="claude-3-sonnet",
                instructions="Read-only research assistant.",
                tools=ToolPolicy(profile="minimal"),
                dm_scope="per-channel-peer",
            ),
        ],
        routing=RoutingConfig(
            defaults={"agentId": "assistant"},
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord", "peer": {"kind": "dm", "id": "user-42"}},
                    agent_id="coder",
                ),
                RouteBindingConfig(
                    match={"channel": "slack", "teamId": "T-eng"},
                    agent_id="coder",
                ),
                RouteBindingConfig(
                    match={"channel": "research"},
                    agent_id="researcher",
                ),
            ],
        ),
        tools=ToolPolicy(
            profile="full",
            allow=["*"],
            deny=["system_*", "admin_*"],
            by_provider={
                "anthropic": ToolPolicy(deny=["sessions_spawn"]),
            },
        ),
        sandbox=SandboxConfig(
            enabled=False,
            safe_bins=["git", "ls", "cat"],
            denied_tools=["exec"],
            subagent_denied_tools=["write", "bash", "git_add", "git_commit"],
            path_restriction=PathRestrictionConfig(
                enabled=True,
                allowed_paths=["/project", "/tmp"],
                denied_paths=["/etc", "/root", "~/.ssh"],
            ),
        ),
        session=SessionConfig(
            sessions_dir="data/sessions",
            max_messages=200,
        ),
        approval=ToolApprovalConfig(
            require_approval=["delete", "git_push"],
            skip_approval=["write"],
        ),
    )


# === Phase 1: Configuration ================================================


def demo_phase1_config() -> MoltbotConfig:
    """Demonstrate config schema construction and validation."""
    header("Phase 1: Configuration System")

    # 1a. Build config programmatically
    sub("1a. Programmatic Config Construction")
    config = build_config()
    ok(f"Created config with {len(config.agents)} agents")
    for a in config.agents:
        info(f"Agent '{a.id}': model={a.model}, dm_scope={a.dm_scope}")
    info(f"Routing: default={config.routing.defaults['agentId']}, "
         f"{len(config.routing.bindings)} bindings")
    info(f"Session: dir={config.session.sessions_dir}, max={config.session.max_messages}")
    info(f"Sandbox: enabled={config.sandbox.enabled}")
    info(f"Approval: require={config.approval.require_approval}, "
         f"skip={config.approval.skip_approval}")

    # 1b. YAML loading (if config file exists)
    sub("1b. YAML Config Loading")
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "agents" / "config.yaml"
    if config_path.exists():
        parser = ConfigParser(str(config_path))
        yaml_config = parser.load()
        ok(f"Loaded {len(yaml_config.agents)} agents from {config_path.name}")
        for a in yaml_config.agents:
            info(f"  {a.id}: {a.name} (model={a.model})")
    else:
        info(f"Config file not found at {config_path} (skipping YAML demo)")

    # 1c. Config validation
    sub("1c. Schema Validation")
    try:
        MoltbotConfig(
            agents=[],
            routing=RoutingConfig(defaults={"agentId": "x"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(),
        )
        info("ERROR: Should have raised ValueError")
    except ValueError as e:
        ok(f"Empty agents rejected: {e}")

    try:
        AgentConfig(id="x", name="x", model="m", dm_scope="invalid")
        info("ERROR: Should have raised ValueError")
    except ValueError as e:
        ok(f"Invalid dm_scope rejected: {e}")

    try:
        ToolPolicy(profile="nonexistent")
        info("ERROR: Should have raised ValueError")
    except ValueError as e:
        ok(f"Invalid profile rejected: {e}")

    # 1d. Path restriction config
    sub("1d. Path Restriction Config")
    pr = config.sandbox.path_restriction
    ok(f"enabled={pr.enabled}, allowed={pr.allowed_paths}, denied={pr.denied_paths}")

    return config


# === Phase 2: Policy Engine ================================================


def demo_phase2_policy(config: MoltbotConfig) -> None:
    """Demonstrate 9-layer cascading tool policy engine."""
    header("Phase 2: Tool Policy Engine (9 Layers)")

    # Build mock tools matching all 30 registered tools
    registry = ToolsRegistry()
    tool_names = registry.list_names()
    tools = []
    for name in tool_names:
        t = MagicMock(spec=FunctionTool)
        t.name = name
        tools.append(t)

    # 2a. Profile presets
    sub("2a. Profile Presets")
    for name, profile in PROFILES.items():
        allow = ", ".join(profile.allow) if profile.allow else "(all)"
        deny = ", ".join(profile.deny) if profile.deny else "(none)"
        info(f"[{name:12s}] allow=[{allow}]  deny=[{deny}]")

    # 2b. Provider detection
    sub("2b. Provider Detection")
    models = [
        "gpt-4o-mini", "gpt-4-turbo", "claude-3-sonnet",
        "llama-3.1-70b", "mistral-7b", "custom-local",
    ]
    for model in models:
        info(f"  {model:25s} -> {detect_provider(model)}")

    # 2c. Per-agent filtering
    sub("2c. Per-Agent Tool Filtering")
    for agent_config in config.agents:
        engine = ToolPolicyEngine(config, agent_config)
        filtered = engine.filter_tools(list(tools))
        names = sorted(t.name for t in filtered)
        info(f"  {agent_config.id:12s}: {len(filtered)}/{len(tools)} tools -> {names}")

    # 2d. Subagent restrictions
    sub("2d. Subagent Restrictions")
    assistant = config.get_agent("assistant")
    engine = ToolPolicyEngine(config, assistant)
    subagent_ctx = PolicyContext(provider="openai", parent_agent_id="parent-123")
    sub_filtered = engine.filter_tools(list(tools), subagent_ctx)
    normal_filtered = engine.filter_tools(list(tools))
    denied = sorted(set(t.name for t in normal_filtered) - set(t.name for t in sub_filtered))
    ok(f"Assistant normal: {len(normal_filtered)} tools")
    ok(f"As sub-agent: {len(sub_filtered)} tools (denied: {denied})")

    # 2e. Sandbox enabled
    sub("2e. Sandbox Impact")
    sandbox_config = MoltbotConfig(
        agents=config.agents,
        routing=config.routing,
        tools=config.tools,
        sandbox=SandboxConfig(
            enabled=True,
            denied_tools=["bash", "delete", "git_push", "git_reset"],
        ),
    )
    engine = ToolPolicyEngine(sandbox_config, assistant)
    sandboxed = engine.filter_tools(list(tools))
    removed = sorted(set(t.name for t in tools) - set(t.name for t in sandboxed))
    ok(f"Sandbox denied: {removed}")
    ok(f"Remaining: {len(sandboxed)} tools")

    # 2f. Provider-specific policy (Anthropic agent)
    sub("2f. Provider-Specific Policy")
    coder = config.get_agent("coder")
    engine_openai = ToolPolicyEngine(config, coder)
    engine_anthropic_ctx = PolicyContext(provider="anthropic")
    filtered_openai = engine_openai.filter_tools(list(tools))
    filtered_anthropic = engine_openai.filter_tools(list(tools), engine_anthropic_ctx)
    diff = sorted(set(t.name for t in filtered_openai) - set(t.name for t in filtered_anthropic))
    ok(f"Coder (openai):    {len(filtered_openai)} tools")
    ok(f"Coder (anthropic): {len(filtered_anthropic)} tools (extra denied: {diff})")


# === Phase 3: Routing ======================================================


async def demo_phase3_routing(config: MoltbotConfig) -> None:
    """Demonstrate 5-tier routing with session key generation."""
    header("Phase 3: Agent Routing (5-Tier Binding + Fallback)")

    router = AgentRouter(config)

    scenarios = [
        ("3a. Discord DM from user-42 (peer match)", RouteContext(
            channel="discord",
            peer=RoutePeer(kind="dm", id="user-42"),
            message="Fix the bug in auth.py",
        )),
        ("3b. Slack from eng team (team match)", RouteContext(
            channel="slack",
            team_id="T-eng",
            peer=RoutePeer(kind="channel", id="general"),
        )),
        ("3c. Research channel (channel match)", RouteContext(
            channel="research",
            peer=RoutePeer(kind="channel", id="papers"),
        )),
        ("3d. Unknown channel (default fallback)", RouteContext(
            channel="telegram",
            peer=RoutePeer(kind="dm", id="user-99"),
            message="Hello!",
        )),
        ("3e. Discord other user (default fallback)", RouteContext(
            channel="discord",
            peer=RoutePeer(kind="dm", id="user-99"),
        )),
    ]

    for title, context in scenarios:
        sub(title)
        route = await router.resolve(context)
        info(f"agent_id:    {route.agent_id}")
        info(f"matched_by:  {route.matched_by}")
        info(f"session_key: {route.session_key}")
        agent_cfg = route.agent_config
        info(f"agent_name:  {agent_cfg.name if agent_cfg else '(not found)'}")
        info(f"dm_scope:    {agent_cfg.dm_scope if agent_cfg else 'N/A'}")

    # 3f. Session key isolation
    sub("3f. Session Key Isolation Comparison")
    peer_scope = RouteContext(
        channel="discord",
        peer=RoutePeer(kind="dm", id="alice"),
    )
    route_a = await router.resolve(peer_scope)
    peer_scope_2 = RouteContext(
        channel="discord",
        peer=RoutePeer(kind="dm", id="bob"),
    )
    route_b = await router.resolve(peer_scope_2)
    ok(f"alice session: {route_a.session_key}")
    ok(f"bob   session: {route_b.session_key}")
    ok(f"Different keys: {route_a.session_key != route_b.session_key}")


# === Phase 4: Sessions =====================================================


def demo_phase4_sessions() -> None:
    """Demonstrate JSONL session persistence."""
    header("Phase 4: Session Persistence (JSONL)")

    tmpdir = tempfile.mkdtemp(prefix="echomind_sessions_")

    try:
        manager = SessionManager(sessions_dir=tmpdir)

        # 4a. Create session
        sub("4a. Create Session")
        session_key = "assistant:discord:alice"
        session_id = manager.create_session(
            session_key=session_key,
            agent_id="assistant",
            cwd="/project",
        )
        ok(f"Created session: {session_id}")
        ok(f"File exists: {manager.session_exists(session_key)}")

        # 4b. Append messages
        sub("4b. Append Messages")
        messages = [
            ("user", "What files are in the project?"),
            ("assistant", "Let me check using the `glob` tool."),
            ("tool", '{"name": "glob", "result": "src/main.py\\nsrc/utils.py"}'),
            ("assistant", "I found 2 Python files: main.py and utils.py"),
            ("user", "Show me main.py"),
            ("assistant", 'Here\'s the content of main.py:\n```python\nprint("hello")\n```'),
        ]
        last_id = None
        for role, content in messages:
            last_id = manager.append_message(
                session_key=session_key,
                role=role,
                content=content,
                parent_id=last_id,
            )
        ok(f"Appended {len(messages)} messages")

        # 4c. Load history
        sub("4c. Load Full History")
        history = manager.load_history(session_key)
        ok(f"Loaded {len(history)} messages")
        for entry in history:
            preview = (entry.content or "")[:60]
            info(f"  [{entry.role:10s}] {preview}...")

        # 4d. Load with max_messages
        sub("4d. Load With max_messages=3")
        recent = manager.load_history(session_key, max_messages=3)
        ok(f"Loaded {len(recent)} most recent messages")
        for entry in recent:
            preview = (entry.content or "")[:60]
            info(f"  [{entry.role:10s}] {preview}...")

        # 4e. Load header
        sub("4e. Load Session Header")
        hdr = manager.load_header(session_key)
        if hdr:
            ok(f"Session ID: {hdr.id}")
            ok(f"Agent: {hdr.agent_id}")
            ok(f"Key: {hdr.session_key}")
            ok(f"Created: {hdr.timestamp}")

        # 4f. Verify JSONL format
        sub("4f. JSONL File Format")
        session_file = manager._get_session_file(session_key)
        with open(session_file) as f:
            lines = f.readlines()
        ok(f"File has {len(lines)} lines (1 header + {len(lines) - 1} messages)")
        first = json.loads(lines[0])
        info(f"  Header type: {first.get('type')}")
        second = json.loads(lines[1])
        info(f"  First msg type: {second.get('type')}, role: {second.get('role')}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# === Phase 5: Tools System =================================================


def demo_phase5_tools() -> None:
    """Demonstrate all 30 tools, approval modes, and path middleware."""
    header("Phase 5: Tools System (30 Tools + Middleware)")

    # 5a. Registry overview
    sub("5a. Tool Registry — 30 Tools")
    registry = ToolsRegistry()
    ok(f"Total tools registered: {registry.count()}")

    # Group by category
    categories = {
        "Filesystem":     ["read", "write", "grep", "glob"],
        "Edit":           ["edit"],
        "Directory":      ["list_dir", "tree", "mkdir", "move", "delete"],
        "Execution":      ["bash"],
        "Web":            ["http_request"],
        "Git (core)":     ["git_log", "git_diff", "git_status", "git_add", "git_commit"],
        "Git (extended)": ["git_branch", "git_checkout", "git_stash", "git_push",
                           "git_pull", "git_reset", "git_clone", "git_tag"],
        "System":         ["env_get", "which", "find_replace"],
        "Text":           ["diff", "patch"],
    }
    for cat, names in categories.items():
        modes = []
        for n in names:
            tool = registry.get(n)
            mode = getattr(tool, "approval_mode", "?")
            modes.append(f"{n}({'A' if mode == 'always_require' else 'N'})")
        info(f"  {cat:18s}: {', '.join(modes)}")
    info("")
    info("  Legend: (A)=always_require  (N)=never_require")

    # 5b. Approval modes
    sub("5b. Approval Gates")
    destructive = [n for n in registry.list_names()
                   if getattr(registry.get(n), "approval_mode", "") == "always_require"]
    safe = [n for n in registry.list_names()
            if getattr(registry.get(n), "approval_mode", "") == "never_require"]
    ok(f"Destructive (always_require): {len(destructive)} tools")
    info(f"    {destructive}")
    ok(f"Safe (never_require): {len(safe)} tools")
    info(f"    {safe}")

    # 5c. Tool filtering with registry
    sub("5c. Registry Filtering (allow/deny patterns)")
    git_only = registry.get_filtered(allow=["git_*"])
    ok(f"allow=['git_*']: {len(git_only)} tools")

    no_git = registry.get_filtered(deny=["git_*"])
    ok(f"deny=['git_*']: {len(no_git)} tools")

    code_tools = registry.get_filtered(allow=["read", "write", "edit", "grep", "glob", "diff", "patch"])
    ok(f"Coding subset: {len(code_tools)} tools")

    # 5d. Live tool execution (filesystem tools)
    sub("5d. Live Tool Execution (read, write, edit, list_dir, tree)")
    tmpdir = tempfile.mkdtemp(prefix="echomind_tools_")
    try:
        # write
        write_tool = registry.get("write")
        result = write_tool.func(path=f"{tmpdir}/hello.py", content='print("hello world")\n')
        ok(f"write: {result}")

        # read
        read_tool = registry.get("read")
        result = read_tool.func(path=f"{tmpdir}/hello.py")
        ok(f"read: {result.strip()}")

        # edit
        edit_tool = registry.get("edit")
        result = edit_tool.func(
            path=f"{tmpdir}/hello.py",
            old_string='print("hello world")',
            new_string='print("hello echomind")',
        )
        ok(f"edit: {result[:80]}...")

        # verify edit
        result = read_tool.func(path=f"{tmpdir}/hello.py")
        ok(f"after edit: {result.strip()}")

        # list_dir
        list_dir_tool = registry.get("list_dir")
        result = list_dir_tool.func(path=tmpdir)
        ok(f"list_dir: {result.strip()}")

        # mkdir
        mkdir_tool = registry.get("mkdir")
        result = mkdir_tool.func(path=f"{tmpdir}/subdir/nested")
        ok(f"mkdir: {result}")

        # tree
        tree_tool = registry.get("tree")
        # write more files for a better tree
        write_tool.func(path=f"{tmpdir}/subdir/nested/data.txt", content="data")
        write_tool.func(path=f"{tmpdir}/README.md", content="# Readme")
        result = tree_tool.func(path=tmpdir)
        info(f"  tree output:")
        for line in result.split("\n"):
            info(f"    {line}")

        # diff
        write_tool.func(path=f"{tmpdir}/a.txt", content="line1\nline2\nline3\n")
        write_tool.func(path=f"{tmpdir}/b.txt", content="line1\nmodified\nline3\n")
        diff_tool = registry.get("diff")
        result = diff_tool.func(file_a=f"{tmpdir}/a.txt", file_b=f"{tmpdir}/b.txt")
        ok(f"diff:")
        for line in result.split("\n")[:6]:
            info(f"    {line}")

        # move
        move_tool = registry.get("move")
        result = move_tool.func(source=f"{tmpdir}/README.md", destination=f"{tmpdir}/DOCS.md")
        ok(f"move: {result}")

        # delete
        delete_tool = registry.get("delete")
        result = delete_tool.func(path=f"{tmpdir}/DOCS.md")
        ok(f"delete: {result}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # 5e. System tools
    sub("5e. System Tools (env_get, which)")
    env_tool = registry.get("env_get")

    # Set a test env var
    os.environ["TEST_DEMO_VAR"] = "echomind_demo_value"
    result = env_tool.func(name="TEST_DEMO_VAR")
    ok(f"env_get(TEST_DEMO_VAR): {result}")
    del os.environ["TEST_DEMO_VAR"]

    # Sensitive var blocking
    result = env_tool.func(name="DB_PASSWORD")
    ok(f"env_get(DB_PASSWORD): {result}")

    which_tool = registry.get("which")
    result = which_tool.func(command="python3")
    ok(f"which(python3): {result}")

    # 5f. Web tool (mock-free, just validation)
    sub("5f. Web Tool (validation)")
    http_tool = registry.get("http_request")
    result = http_tool.func(url="https://example.com", method="DELETE")
    ok(f"Invalid method blocked: {result[:60]}")

    # 5g. Git safety
    sub("5g. Git Safety Checks")
    git_reset = registry.get("git_reset")
    result = git_reset.func(mode="hard")
    ok(f"git_reset --hard rejected: {result[:70]}")

    git_branch = registry.get("git_branch")
    result = git_branch.func(action="invalid")
    ok(f"git_branch invalid action: {result[:60]}")

    git_stash = registry.get("git_stash")
    result = git_stash.func(action="invalid")
    ok(f"git_stash invalid action: {result[:60]}")


# === Phase 5b: Path Restriction Middleware ==================================


async def demo_phase5_middleware() -> None:
    """Demonstrate PathRestrictionMiddleware."""
    header("Phase 5b: Path Restriction Middleware")

    from pydantic import BaseModel, Field

    class ReadArgs(BaseModel):
        """Arguments for read tool."""
        path: str = Field(description="File path")

    class MoveArgs(BaseModel):
        """Arguments for move tool."""
        source: str = Field(description="Source path")
        destination: str = Field(description="Destination path")

    class NoPathArgs(BaseModel):
        """Arguments for a tool with no path."""
        query: str = Field(description="Search query")

    middleware = PathRestrictionMiddleware(
        allowed_paths=["/project", "/tmp"],
        denied_paths=["/etc", "/root"],
    )

    async def make_call_next() -> None:
        """Mock call_next that does nothing."""

    # Test scenarios
    scenarios = [
        ("Allowed path (/project/src/main.py)", ReadArgs(path="/project/src/main.py"), True),
        ("Allowed path (/tmp/test.txt)", ReadArgs(path="/tmp/test.txt"), True),
        ("Denied path (/etc/passwd)", ReadArgs(path="/etc/passwd"), False),
        ("Denied path (/root/.bashrc)", ReadArgs(path="/root/.bashrc"), False),
        ("Outside allowed (/home/user/file)", ReadArgs(path="/home/user/file"), False),
        ("No path args (always allowed)", NoPathArgs(query="search term"), True),
    ]

    sub("Path Restriction Scenarios")
    for title, args, should_pass in scenarios:
        mock_fn = MagicMock(spec=FunctionTool)
        mock_fn.name = "test_tool"
        ctx = FunctionInvocationContext(function=mock_fn, arguments=args)

        call_next_called = False
        async def tracked_call_next(
            _called=[False],  # noqa: B006 — mutable default for closure
        ) -> None:
            _called[0] = True

        # Reset closure state
        tracked_call_next.__defaults__ = ([False],)
        await middleware.process(ctx, tracked_call_next)

        passed = ctx.result is None
        status = "PASS" if passed == should_pass else "FAIL"
        symbol = "[OK]" if status == "PASS" else "[!!]"
        blocked_msg = f" -> blocked: {ctx.result[:50]}..." if ctx.result else ""
        info(f"  {symbol} {title}: {'allowed' if passed else 'blocked'}{blocked_msg}")

    # Multi-path check (move has source + destination)
    sub("Multi-Path Validation (move tool)")
    mock_fn = MagicMock(spec=FunctionTool)
    mock_fn.name = "move"

    # Both paths allowed
    ctx = FunctionInvocationContext(
        function=mock_fn,
        arguments=MoveArgs(source="/project/a.txt", destination="/project/b.txt"),
    )
    await middleware.process(ctx, make_call_next)
    ok(f"Both in /project: {'allowed' if ctx.result is None else 'blocked'}")

    # Destination denied
    ctx = FunctionInvocationContext(
        function=mock_fn,
        arguments=MoveArgs(source="/project/a.txt", destination="/etc/evil.txt"),
    )
    await middleware.process(ctx, make_call_next)
    ok(f"Dest in /etc: {'allowed' if ctx.result is None else 'blocked'}")


# === Integration: Full Pipeline =============================================


async def demo_integration(config: MoltbotConfig) -> None:
    """Demonstrate the full pipeline: route -> policy -> session -> tools."""
    header("Integration: Full Request Pipeline")

    tmpdir = tempfile.mkdtemp(prefix="echomind_integration_")

    try:
        # Step 1: Route the message
        sub("Step 1: Route Incoming Message")
        router = AgentRouter(config)
        context = RouteContext(
            channel="discord",
            peer=RoutePeer(kind="dm", id="user-42"),
            message="Refactor the utils module",
        )
        route = await router.resolve(context)
        ok(f"Routed to: {route.agent_id} (matched_by={route.matched_by})")
        ok(f"Session key: {route.session_key}")

        # Step 2: Apply policy
        sub("Step 2: Apply Tool Policy")
        agent_config = route.agent_config
        registry = ToolsRegistry()
        tools = []
        for name in registry.list_names():
            t = MagicMock(spec=FunctionTool)
            t.name = name
            tools.append(t)

        engine = ToolPolicyEngine(config, agent_config)
        filtered = engine.filter_tools(tools)
        ok(f"Policy: {len(tools)} -> {len(filtered)} tools for '{agent_config.id}'")
        info(f"  Available: {sorted(t.name for t in filtered)}")

        # Step 3: Create session
        sub("Step 3: Create/Load Session")
        manager = SessionManager(sessions_dir=tmpdir)
        session_id = manager.create_session(
            session_key=route.session_key,
            agent_id=route.agent_id,
        )
        ok(f"Session created: {session_id}")

        # Simulate a conversation
        manager.append_message(route.session_key, "user", "Refactor the utils module")
        manager.append_message(
            route.session_key, "assistant",
            "I'll read the current utils module first."
        )
        manager.append_message(
            route.session_key, "tool",
            '{"name": "read", "args": {"path": "src/utils.py"}}'
        )
        manager.append_message(
            route.session_key, "assistant",
            "I've refactored the utils module. Here are the changes..."
        )
        history = manager.load_history(route.session_key)
        ok(f"Conversation: {len(history)} messages")

        # Step 4: Check approval requirements
        sub("Step 4: Check Approval Requirements")
        for tool_name in ["read", "write", "edit", "bash", "git_push", "delete"]:
            tool = registry.get(tool_name)
            mode = getattr(tool, "approval_mode", "?")
            symbol = "🔒" if mode == "always_require" else "🔓"
            info(f"  {symbol} {tool_name:15s} -> {mode}")

        # Step 5: Path middleware
        sub("Step 5: Path Restriction Check")
        ok(f"Path restriction enabled: {config.sandbox.path_restriction.enabled}")
        ok(f"Allowed: {config.sandbox.path_restriction.allowed_paths}")
        ok(f"Denied:  {config.sandbox.path_restriction.denied_paths}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# === Summary ================================================================


def demo_summary() -> None:
    """Print final summary of all demonstrated features."""
    header("Feature Summary")

    features = [
        ("Phase 1", "Configuration", [
            "YAML config loading with env var expansion",
            "Dataclass-based schema with validation",
            "ToolApprovalConfig & PathRestrictionConfig",
            "Agent, Routing, Sandbox, Session configs",
        ]),
        ("Phase 2", "Policy Engine", [
            "9-layer cascading filter (profile -> global -> agent -> sandbox -> subagent)",
            "4 profile presets (minimal/coding/messaging/full)",
            "Provider detection (openai/anthropic/meta/mistral/local)",
            "Per-provider policy overrides (byProvider)",
            "Sandbox tool denial",
            "Subagent tool restrictions",
        ]),
        ("Phase 3", "Routing", [
            "5-tier binding hierarchy (peer > guild > team > account > channel)",
            "Default agent fallback",
            "Intent classification support (LLM-based)",
            "Session key generation with dm_scope isolation",
        ]),
        ("Phase 4", "Sessions", [
            "JSONL file-based persistence",
            "Session header + message entries",
            "max_messages history truncation",
            "JSONLHistoryProvider for framework integration",
        ]),
        ("Phase 5", "Tools System", [
            "30 tools across 9 categories",
            "Approval gates (always_require / never_require)",
            "PathRestrictionMiddleware (allowed/denied paths)",
            "Config-level approval overrides",
            "Security: git_reset rejects --hard, env_get blocks secrets",
            "Security: http_request blocks auth headers",
        ]),
    ]

    for phase, title, items in features:
        sub(f"{phase}: {title}")
        for item in items:
            info(f"  {item}")

    registry = ToolsRegistry()
    print(f"\n  Total tools: {registry.count()}")
    print(f"  Total features demonstrated: {sum(len(items) for _, _, items in features)}")


# === Main ===================================================================


async def main() -> None:
    """Run all feature demonstrations."""
    print("\n" + "=" * 70)
    print("  EchoMind Agent System — Full Feature Showcase")
    print("  Phases 1-5: Config, Policy, Routing, Sessions, Tools")
    print("=" * 70)

    # Phase 1
    config = demo_phase1_config()

    # Phase 2
    demo_phase2_policy(config)

    # Phase 3
    await demo_phase3_routing(config)

    # Phase 4
    demo_phase4_sessions()

    # Phase 5
    demo_phase5_tools()
    await demo_phase5_middleware()

    # Integration
    await demo_integration(config)

    # Summary
    demo_summary()

    print(f"\n{'=' * 70}")
    print("  All demonstrations completed successfully.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
