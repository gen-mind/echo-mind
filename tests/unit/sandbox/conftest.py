"""Shared fixtures for sandbox tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.sandbox.backend import SandboxBackend
from api.sandbox.config import SandboxSettings, get_sandbox_settings
from api.sandbox.models import ContainerInfo, SandboxState, WarmContainer


class MockSandboxBackend(SandboxBackend):
    """In-memory mock backend for testing."""

    def __init__(self) -> None:
        """Initialize mock backend."""
        self.containers: dict[str, ContainerInfo] = {}
        self.env_injections: dict[str, dict[str, str]] = {}
        self._counter = 0

    async def create_container(
        self,
        name: str,
        image: str,
        env: dict[str, str],
        network: str,
        cpu_limit: float,
        memory_limit: str,
        labels: dict[str, str] | None = None,
    ) -> ContainerInfo:
        """Create mock container."""
        self._counter += 1
        container_id = f"mock-{self._counter:04d}"
        info = ContainerInfo(
            container_id=container_id,
            name=name,
            status="created",
            labels=labels or {},
        )
        self.containers[container_id] = info
        return info

    async def start_container(self, container_id: str) -> None:
        """Start mock container."""
        if container_id not in self.containers:
            raise RuntimeError(f"Container {container_id} not found")
        self.containers[container_id].status = "running"

    async def stop_container(self, container_id: str, timeout: int = 5) -> None:
        """Stop mock container."""
        if container_id in self.containers:
            self.containers[container_id].status = "exited"

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove mock container."""
        self.containers.pop(container_id, None)

    async def get_container(self, container_id: str) -> ContainerInfo | None:
        """Get mock container."""
        return self.containers.get(container_id)

    async def list_containers(self, labels: dict[str, str]) -> list[ContainerInfo]:
        """List mock containers matching labels."""
        result = []
        for info in self.containers.values():
            match = all(info.labels.get(k) == v for k, v in labels.items())
            if match:
                result.append(info)
        return result

    async def inject_env(self, container_id: str, env: dict[str, str]) -> None:
        """Inject env into mock container."""
        if container_id not in self.containers:
            raise RuntimeError(f"Container {container_id} not found")
        self.env_injections[container_id] = env


@pytest.fixture
def mock_backend() -> MockSandboxBackend:
    """Create a mock sandbox backend."""
    return MockSandboxBackend()


@pytest.fixture
def sandbox_settings() -> SandboxSettings:
    """Create test sandbox settings."""
    return SandboxSettings(
        pool_size=2,
        max_instances=5,
        idle_timeout=300,
        session_timeout=3600,
        image="test-sandbox:latest",
        network="test-sandbox",
        cpu_limit=1.0,
        memory_limit="512m",
        reconciliation_interval=5,
        nats_url="nats://localhost:4222",
        mcp_url="http://localhost:8100",
    )


@pytest.fixture
def container_info() -> ContainerInfo:
    """Create a test container info."""
    return ContainerInfo(
        container_id="abc123def456",
        name="sandbox-test-001",
        status="running",
        labels={"echomind.sandbox": "true"},
    )


@pytest.fixture
def warm_container() -> WarmContainer:
    """Create a test warm container."""
    return WarmContainer(
        container_id="warm-001",
        container_name="sandbox-warm-001",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def _reset_sandbox_settings() -> None:
    """Reset sandbox settings singleton before each test."""
    get_sandbox_settings.cache_clear()
    yield  # type: ignore[misc]
    get_sandbox_settings.cache_clear()
