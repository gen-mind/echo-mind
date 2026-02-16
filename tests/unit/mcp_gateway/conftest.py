"""Shared fixtures for MCP Gateway tests."""

import pytest

from mcp_gateway.config import reset_settings


@pytest.fixture(autouse=True)
def _reset_settings_singleton() -> None:
    """Reset settings singleton before each test to ensure isolation."""
    reset_settings()
    yield  # type: ignore[misc]
    reset_settings()
