"""
Multi-agent policy demo — shows how different agents get different tools.

This example demonstrates:
- Loading 3 agents (assistant, coder, researcher) from config
- 9-layer policy engine filtering tools per agent
- Comparing tool sets across agents and profiles
- Running each agent with the same prompt to see behavioral differences
- Subagent context restricting tools further

Usage:
    cd src/agent/examples/
    python multi_agent_policy_example.py
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src/ to path so 'agent' resolves as a package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

# Load API key from agent/.env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agent.agent import AgentFactory, AgentRunRequest
from agent.config.parser import ConfigParser
from agent.config.schema import AgentConfig, MoltbotConfig, ToolPolicy
from agent.policy.engine import PolicyContext, ToolPolicyEngine
from agent.policy.profiles import PROFILES
from agent.policy.providers import detect_provider


def print_header(title: str) -> None:
    """Print a formatted section header."""
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_subheader(title: str) -> None:
    """Print a formatted subsection header."""
    print(f"\n  --- {title} ---")


def demo_profiles() -> None:
    """Show all available profile presets and their tool patterns."""
    print_header("1. Profile Presets")

    for name, profile in PROFILES.items():
        allow_str = ", ".join(profile.allow) if profile.allow else "(none)"
        deny_str = ", ".join(profile.deny) if profile.deny else "(none)"
        print(f"\n  [{name}]")
        print(f"    allow: {allow_str}")
        print(f"    deny:  {deny_str}")


def demo_provider_detection() -> None:
    """Show how provider detection works for different model names."""
    print_header("2. Provider Detection")

    models = [
        "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o3-mini",
        "claude-3-sonnet", "claude-3-haiku",
        "llama-3.1-70b", "mistral-7b", "custom-local-model",
    ]

    for model in models:
        provider = detect_provider(model)
        print(f"  {model:30s} -> {provider}")


def demo_policy_filtering(config: MoltbotConfig) -> None:
    """Show how the policy engine filters tools for each agent."""
    print_header("3. Policy Engine — Tool Filtering Per Agent")

    # Create mock tools matching our 10 core tools
    from unittest.mock import MagicMock
    from agent_framework import FunctionTool

    tool_names = [
        "read", "write", "grep", "glob", "bash",
        "git_log", "git_diff", "git_status", "git_add", "git_commit",
    ]
    tools = []
    for name in tool_names:
        t = MagicMock(spec=FunctionTool)
        t.name = name
        tools.append(t)

    for agent_config in config.agents:
        engine = ToolPolicyEngine(config, agent_config)

        # Normal filtering
        filtered = engine.filter_tools(list(tools))
        filtered_names = sorted(t.name for t in filtered)

        print_subheader(f"{agent_config.name} (id={agent_config.id})")
        print(f"    model:    {agent_config.model}")
        print(f"    provider: {engine.provider}")
        if agent_config.tools:
            print(f"    profile:  {agent_config.tools.profile or '(none)'}")
            print(f"    allow:    {agent_config.tools.allow or '(none)'}")
            print(f"    deny:     {agent_config.tools.deny or '(none)'}")
        else:
            print(f"    policy:   (none)")
        print(f"    tools:    {len(filtered)}/10 -> {filtered_names}")

        # Subagent filtering
        subagent_ctx = PolicyContext(
            provider=engine.provider,
            parent_agent_id="parent-agent",
        )
        subagent_filtered = engine.filter_tools(list(tools), subagent_ctx)
        subagent_names = sorted(t.name for t in subagent_filtered)

        denied_as_subagent = sorted(
            set(filtered_names) - set(subagent_names)
        )
        print(f"    as subagent: {len(subagent_filtered)} tools "
              f"(denied: {denied_as_subagent})")


def demo_sandbox_impact(config: MoltbotConfig) -> None:
    """Show what happens when sandbox is enabled."""
    print_header("4. Sandbox Impact (Simulated)")

    from unittest.mock import MagicMock
    from agent_framework import FunctionTool
    from agent.config.schema import RoutingConfig, SandboxConfig

    tool_names = [
        "read", "write", "grep", "glob", "bash",
        "git_log", "git_diff", "git_status", "git_add", "git_commit",
    ]
    tools = []
    for name in tool_names:
        t = MagicMock(spec=FunctionTool)
        t.name = name
        tools.append(t)

    # Simulate sandbox enabled
    sandbox_config = MoltbotConfig(
        agents=config.agents,
        routing=config.routing,
        tools=config.tools,
        sandbox=SandboxConfig(
            enabled=True,
            denied_tools=["bash", "write", "git_commit", "git_add"],
            subagent_denied_tools=config.sandbox.subagent_denied_tools,
        ),
    )

    assistant = sandbox_config.get_agent("assistant")
    engine = ToolPolicyEngine(sandbox_config, assistant)

    before = sorted(t.name for t in tools)
    filtered = engine.filter_tools(list(tools))
    after = sorted(t.name for t in filtered)
    denied = sorted(set(before) - set(after))

    print(f"\n  Sandbox enabled with denied_tools: {sandbox_config.sandbox.denied_tools}")
    print(f"  Before: {len(before)} tools -> {before}")
    print(f"  After:  {len(after)} tools  -> {after}")
    print(f"  Denied: {denied}")


async def demo_multi_agent_run(config: MoltbotConfig) -> None:
    """Run the same prompt through all 3 agents and compare responses."""
    print_header("5. Multi-Agent Execution (Live API Calls)")

    factory = AgentFactory(global_config=config)
    prompt = "What tools do you have access to? List them briefly."

    for agent_config in config.agents:
        print_subheader(f"{agent_config.name}")

        agent = factory.create_agent(agent_config)

        print(f"    Prompt: {prompt}")

        start = time.time()
        request = AgentRunRequest(input=prompt)
        response = await agent.run(request)
        elapsed = time.time() - start

        # Truncate long responses
        output = response.output
        if len(output) > 300:
            output = output[:300] + "..."

        print(f"    Response ({elapsed:.1f}s):")
        for line in output.split("\n"):
            print(f"      {line}")

        if response.usage:
            total = response.usage.get("total_tokens", 0)
            print(f"    Tokens: {total}")


async def main() -> None:
    """Run the full multi-agent policy demo."""
    config_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "config" / "agents" / "config.yaml"
    )
    print(f"📖 Loading config from {config_path.name}")

    parser = ConfigParser(str(config_path))
    config = parser.load()

    print(f"✅ Loaded {len(config.agents)} agents: "
          f"{[a.id for a in config.agents]}")

    # Parts 1-4 are offline (no API calls)
    demo_profiles()
    demo_provider_detection()
    demo_policy_filtering(config)
    demo_sandbox_impact(config)

    # Part 5 makes real API calls
    print_header("5. Multi-Agent Execution (Live API Calls)")

    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("\n  Skipped: OPENAI_API_KEY not set.")
        print("  Parts 1-4 above work without an API key.")
        return

    await demo_multi_agent_run(config)

    print_header("Done")
    print("\n  All demos completed successfully.\n")


if __name__ == "__main__":
    asyncio.run(main())
