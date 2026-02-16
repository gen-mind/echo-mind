"""Tests for abstract SandboxBackend contract using MockSandboxBackend."""

import pytest

from tests.unit.sandbox.conftest import MockSandboxBackend


class TestSandboxBackendContract:
    """Contract tests that any SandboxBackend implementation must pass."""

    @pytest.fixture
    def backend(self) -> MockSandboxBackend:
        """Create mock backend for contract testing."""
        return MockSandboxBackend()

    @pytest.mark.asyncio
    async def test_create_container(self, backend: MockSandboxBackend) -> None:
        """Test creating a container returns valid ContainerInfo."""
        info = await backend.create_container(
            name="test-container",
            image="test:latest",
            env={"KEY": "value"},
            network="test-net",
            cpu_limit=1.0,
            memory_limit="512m",
            labels={"app": "test"},
        )
        assert info.container_id
        assert info.name == "test-container"
        assert info.labels.get("app") == "test"

    @pytest.mark.asyncio
    async def test_start_container(self, backend: MockSandboxBackend) -> None:
        """Test starting a created container."""
        info = await backend.create_container(
            name="test", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
        )
        await backend.start_container(info.container_id)
        updated = await backend.get_container(info.container_id)
        assert updated is not None
        assert updated.status == "running"

    @pytest.mark.asyncio
    async def test_start_nonexistent_raises(self, backend: MockSandboxBackend) -> None:
        """Test starting nonexistent container raises RuntimeError."""
        with pytest.raises(RuntimeError):
            await backend.start_container("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_container(self, backend: MockSandboxBackend) -> None:
        """Test stopping a running container."""
        info = await backend.create_container(
            name="test", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
        )
        await backend.start_container(info.container_id)
        await backend.stop_container(info.container_id)
        updated = await backend.get_container(info.container_id)
        assert updated is not None
        assert updated.status == "exited"

    @pytest.mark.asyncio
    async def test_remove_container(self, backend: MockSandboxBackend) -> None:
        """Test removing a container."""
        info = await backend.create_container(
            name="test", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
        )
        await backend.remove_container(info.container_id)
        assert await backend.get_container(info.container_id) is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, backend: MockSandboxBackend) -> None:
        """Test getting nonexistent container returns None."""
        assert await backend.get_container("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_containers_by_label(self, backend: MockSandboxBackend) -> None:
        """Test listing containers filtered by labels."""
        await backend.create_container(
            name="match", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
            labels={"app": "sandbox"},
        )
        await backend.create_container(
            name="no-match", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
            labels={"app": "other"},
        )
        results = await backend.list_containers({"app": "sandbox"})
        assert len(results) == 1
        assert results[0].name == "match"

    @pytest.mark.asyncio
    async def test_inject_env(self, backend: MockSandboxBackend) -> None:
        """Test injecting environment variables."""
        info = await backend.create_container(
            name="test", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
        )
        await backend.inject_env(info.container_id, {"SESSION_ID": "abc"})
        assert backend.env_injections[info.container_id] == {"SESSION_ID": "abc"}

    @pytest.mark.asyncio
    async def test_inject_env_nonexistent_raises(self, backend: MockSandboxBackend) -> None:
        """Test injecting env into nonexistent container raises."""
        with pytest.raises(RuntimeError):
            await backend.inject_env("nonexistent", {"KEY": "val"})
