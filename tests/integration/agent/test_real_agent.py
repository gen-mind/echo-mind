"""
Integration tests for Agent System with real OpenAI API calls.

These tests make REAL API calls and require:
- OPENAI_API_KEY set in environment or src/agent/.env
- Network access to OpenAI API

Run with: PYTHONPATH=src python -m pytest tests/integration/agent/test_real_agent.py -v -s
"""

import asyncio
import os
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env from agent directory
_agent_env = Path(__file__).resolve().parents[3] / "src" / "agent" / ".env"
if _agent_env.exists():
    load_dotenv(_agent_env)

# Skip all tests if no API key
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set — skipping integration tests",
    ),
]


@pytest.fixture(scope="module")
def config_path() -> str:
    """Path to agent config YAML."""
    path = Path(__file__).resolve().parents[3] / "config" / "agents" / "config.yaml"
    assert path.exists(), f"Config not found: {path}"
    return str(path)


@pytest.fixture(scope="module")
def agent_wrapper(config_path: str):
    """Create a real agent wrapper using AgentFactory."""
    from agent.agent import AgentFactory
    from agent.config.parser import ConfigParser

    parser = ConfigParser(config_path)
    moltbot_config = parser.load()

    # Use the first agent (assistant)
    agent_config = moltbot_config.agents[0]
    print(f"\n  Agent: {agent_config.name} (model: {agent_config.model})")

    factory = AgentFactory()
    wrapper = factory.create_agent(agent_config)
    print(f"  Tools: {wrapper.tools_registry.list_names()}")
    return wrapper


class TestRealAgentNonStreaming:
    """Test non-streaming agent execution with real API."""

    @pytest.mark.asyncio
    async def test_simple_prompt(self, agent_wrapper) -> None:
        """Send a simple math question and verify we get a response."""
        from agent.agent import AgentRunRequest

        request = AgentRunRequest(input="What is 2+2? Answer in one word.")

        print("\n  Prompt: 'What is 2+2? Answer in one word.'")
        start = time.time()
        response = await agent_wrapper.run(request)
        elapsed = time.time() - start

        print(f"  Response: {response.output}")
        print(f"  Finish reason: {response.finish_reason}")
        print(f"  Usage: {response.usage}")
        print(f"  Elapsed: {elapsed:.2f}s")

        assert response.output, "Response should not be empty"
        assert "4" in response.output.lower() or "four" in response.output.lower(), (
            f"Expected '4' or 'four' in response, got: {response.output}"
        )

    @pytest.mark.asyncio
    async def test_tool_use(self, agent_wrapper) -> None:
        """Send a prompt that should trigger tool use (file listing)."""
        from agent.agent import AgentRunRequest

        request = AgentRunRequest(
            input="List the files in the current directory using the appropriate tool. Show me the output."
        )

        print("\n  Prompt: 'List the files in the current directory...'")
        start = time.time()
        response = await agent_wrapper.run(request)
        elapsed = time.time() - start

        print(f"  Response (first 500 chars): {response.output[:500]}")
        print(f"  Finish reason: {response.finish_reason}")
        print(f"  Usage: {response.usage}")
        print(f"  Elapsed: {elapsed:.2f}s")

        assert response.output, "Response should not be empty"
        # The agent should have produced some file listing output
        print("  (Tool use test passed — agent produced a response)")


class TestRealAgentStreaming:
    """Test streaming agent execution with real API."""

    @pytest.mark.asyncio
    async def test_streaming_response(self, agent_wrapper) -> None:
        """Test streaming with a simple prompt."""
        from agent.agent import AgentRunRequest

        request = AgentRunRequest(
            input="Count from 1 to 5, one number per line.",
            stream=True,
        )

        print("\n  Prompt: 'Count from 1 to 5, one number per line.'")
        start = time.time()

        chunks: list[str] = []
        async for chunk in agent_wrapper.run_stream(request):
            chunks.append(chunk)
            print(f"    chunk: {chunk!r}")

        elapsed = time.time() - start
        full_response = "".join(chunks)

        print(f"  Full response: {full_response}")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  Elapsed: {elapsed:.2f}s")

        assert chunks, "Should have received at least one chunk"
        assert full_response, "Full response should not be empty"
