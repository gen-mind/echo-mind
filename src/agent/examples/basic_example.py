"""
Basic example of using the agent wrapper.

This example demonstrates:
- Loading configuration from YAML
- Creating an agent with the factory
- Running the agent with a simple query

Usage:
    cd src/agent/examples/
    python basic_example.py
"""

import asyncio
import sys
from pathlib import Path

# Add src/ to path so 'agent' resolves as a package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

# Load API key from agent/.env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agent.agent import AgentFactory, AgentRunRequest
from agent.config.parser import ConfigParser


async def main() -> None:
    """Run basic agent example."""
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "agents" / "config.yaml"
    print(f"📖 Loading configuration from {config_path}")

    parser = ConfigParser(str(config_path))
    config = parser.load()

    print(f"✅ Loaded {len(config.agents)} agents:")
    for agent_config in config.agents:
        print(f"  - {agent_config.id}: {agent_config.name} ({agent_config.model})")

    # Create agent factory (with global config for policy engine)
    print("\n🏭 Creating agent factory...")
    factory = AgentFactory(global_config=config)

    # Create the assistant agent
    assistant_config = config.get_agent("assistant")
    if not assistant_config:
        print("❌ Assistant agent not found in config")
        return

    print(f"\n🤖 Creating agent '{assistant_config.name}'...")
    agent = factory.create_agent(assistant_config)

    # Run a simple query
    print("\n💬 Running query: 'What is the capital of France?'")
    request = AgentRunRequest(input="What is the capital of France?")

    response = await agent.run(request)

    print(f"\n🎯 Response:")
    print(f"  {response.output}")

    if response.usage:
        print(f"\n📊 Token usage:")
        print(f"  Prompt: {response.usage.get('prompt_tokens', 0)}")
        print(f"  Completion: {response.usage.get('completion_tokens', 0)}")
        print(f"  Total: {response.usage.get('total_tokens', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
