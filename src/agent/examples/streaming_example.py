"""
Streaming example using the agent wrapper.

This example demonstrates:
- Streaming responses from the agent
- Real-time output display

Usage:
    cd src/agent/examples/
    python streaming_example.py
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
    """Run streaming agent example."""
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "agents" / "config.yaml"
    parser = ConfigParser(str(config_path))
    config = parser.load()

    # Create agent (with global config for policy engine)
    factory = AgentFactory(global_config=config)
    assistant_config = config.get_agent("assistant")
    if not assistant_config:
        print("❌ Assistant agent not found in config")
        return

    agent = factory.create_agent(assistant_config)

    # Run streaming query
    print("💬 Query: 'Write a short poem about AI assistants'\n")
    print("🎯 Response (streaming):\n")

    request = AgentRunRequest(
        input="Write a short poem about AI assistants",
        stream=True,
    )

    # Stream and display chunks in real-time
    async for chunk in agent.run_stream(request):
        print(chunk, end="", flush=True)

    print("\n\n✅ Streaming complete!")


if __name__ == "__main__":
    asyncio.run(main())
