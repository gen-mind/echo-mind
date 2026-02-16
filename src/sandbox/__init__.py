"""
EchoMind Sandbox Agent Service.

Runs inside ephemeral Docker containers. Receives user messages via NATS,
executes an agent (Semantic Kernel + MCP tools), and streams responses back.
"""
