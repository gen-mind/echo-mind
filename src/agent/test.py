"""
Quick test script — call the agent with a prompt.

Usage:
    cd src/agent/
    python test.py
    python test.py "Your custom prompt here"
    python test.py --agent coder "Write a hello world"
    python test.py --agent researcher "What files exist?"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src/ to path so 'agent' resolves as a package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Load API key from .env in this directory
load_dotenv(Path(__file__).parent / ".env")

from agent.agent import AgentFactory, AgentRunRequest
from agent.config.parser import ConfigParser


async def main() -> None:
    """Run an agent with the given prompt."""
    parser = argparse.ArgumentParser(description="Test the agent system")
    parser.add_argument(
        "--agent", "-a",
        default=None,
        help="Agent ID to use (default: first agent in config)",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        default=["What files are in the current directory? List them."],
        help="Prompt to send to the agent",
    )
    args = parser.parse_args()
    prompt = " ".join(args.prompt)

    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "agents" / "config.yaml"
    config = ConfigParser(str(config_path)).load()

    # Select agent
    if args.agent:
        agent_config = config.get_agent(args.agent)
        if not agent_config:
            valid_ids = [a.id for a in config.agents]
            print(f"❌ Agent '{args.agent}' not found. Available: {valid_ids}")
            sys.exit(1)
    else:
        agent_config = config.agents[0]

    factory = AgentFactory(global_config=config)
    agent = factory.create_agent(agent_config)

    print(f"🤖 Agent: {agent_config.name} ({agent_config.model})")
    print(f"🔧 Tools: {factory.tools_registry.list_names()}")
    if agent_config.tools:
        print(f"🔒 Policy: profile={agent_config.tools.profile}, allow={agent_config.tools.allow}, deny={agent_config.tools.deny}")
    print(f"💬 Prompt: {prompt}\n")

    request = AgentRunRequest(input=prompt)
    response = await agent.run(request)

    print(f"🎯 Response:\n{response.output}")


if __name__ == "__main__":
    asyncio.run(main())
