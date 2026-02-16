"""Tests for DockerSandboxBackend with mocked Docker SDK."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.sandbox.docker_backend import DockerSandboxBackend
from api.sandbox.models import ContainerInfo


def _make_mock_container(
    container_id: str = "abc123",
    name: str = "test-container",
    status: str = "running",
    labels: dict[str, str] | None = None,
    short_id: str = "abc123",
) -> MagicMock:
    """Create a mock Docker container."""
    container = MagicMock()
    container.id = container_id
    container.short_id = short_id
    container.name = name
    container.status = status
    container.labels = labels or {}
    return container


class TestDockerSandboxBackendCreate:
    """Tests for container creation."""

    @pytest.mark.asyncio
    async def test_create_container_success(self) -> None:
        """Test successful container creation."""
        mock_client = MagicMock()
        mock_container = _make_mock_container()
        mock_client.containers.create.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        info = await backend.create_container(
            name="sandbox-test",
            image="test:latest",
            env={"KEY": "value"},
            network="test-net",
            cpu_limit=2.0,
            memory_limit="2g",
            labels={"custom": "label"},
        )

        assert info.container_id == "abc123"
        assert info.name == "test-container"
        mock_client.containers.create.assert_called_once()

        call_kwargs = mock_client.containers.create.call_args[1]
        assert call_kwargs["image"] == "test:latest"
        assert call_kwargs["name"] == "sandbox-test"
        assert call_kwargs["network"] == "test-net"
        assert call_kwargs["read_only"] is True
        assert call_kwargs["security_opt"] == ["no-new-privileges"]
        assert call_kwargs["cap_drop"] == ["ALL"]
        assert call_kwargs["cap_add"] == ["NET_RAW"]
        assert call_kwargs["pids_limit"] == 100
        assert call_kwargs["tmpfs"] == {"/tmp": "size=100M,noexec,nosuid,nodev"}
        assert call_kwargs["nano_cpus"] == 2_000_000_000
        assert call_kwargs["mem_limit"] == "2g"

    @pytest.mark.asyncio
    async def test_create_container_includes_sandbox_labels(self) -> None:
        """Test that sandbox labels are always applied."""
        mock_client = MagicMock()
        mock_container = _make_mock_container(labels={"echomind.sandbox": "true"})
        mock_client.containers.create.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        await backend.create_container(
            name="test", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="1g",
        )

        call_kwargs = mock_client.containers.create.call_args[1]
        assert "echomind.sandbox" in call_kwargs["labels"]
        assert call_kwargs["labels"]["echomind.sandbox"] == "true"

    @pytest.mark.asyncio
    async def test_create_container_failure_raises(self) -> None:
        """Test that Docker API errors are wrapped in RuntimeError."""
        from docker.errors import APIError

        mock_client = MagicMock()
        mock_client.containers.create.side_effect = APIError("disk full")

        backend = DockerSandboxBackend(client=mock_client)
        with pytest.raises(RuntimeError, match="Failed to create container"):
            await backend.create_container(
                name="test", image="test:latest", env={},
                network="net", cpu_limit=1.0, memory_limit="1g",
            )


class TestDockerSandboxBackendLifecycle:
    """Tests for start/stop/remove operations."""

    @pytest.mark.asyncio
    async def test_start_container_success(self) -> None:
        """Test starting a container."""
        mock_container = _make_mock_container()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        await backend.start_container("abc123")

        mock_container.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_container_not_found(self) -> None:
        """Test starting a nonexistent container raises RuntimeError."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("not found")

        backend = DockerSandboxBackend(client=mock_client)
        with pytest.raises(RuntimeError, match="not found"):
            await backend.start_container("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_container_success(self) -> None:
        """Test stopping a container."""
        mock_container = _make_mock_container()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        await backend.stop_container("abc123", timeout=10)

        mock_container.stop.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_stop_container_not_found_silent(self) -> None:
        """Test stopping a nonexistent container doesn't raise."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("gone")

        backend = DockerSandboxBackend(client=mock_client)
        # Should not raise
        await backend.stop_container("gone123")

    @pytest.mark.asyncio
    async def test_remove_container_success(self) -> None:
        """Test removing a container."""
        mock_container = _make_mock_container()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        await backend.remove_container("abc123", force=True)

        mock_container.remove.assert_called_once_with(force=True)


class TestDockerSandboxBackendQuery:
    """Tests for get/list/inject operations."""

    @pytest.mark.asyncio
    async def test_get_container_found(self) -> None:
        """Test getting an existing container."""
        mock_container = _make_mock_container()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        info = await backend.get_container("abc123")

        assert info is not None
        assert info.container_id == "abc123"

    @pytest.mark.asyncio
    async def test_get_container_not_found(self) -> None:
        """Test getting a nonexistent container returns None."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("not found")

        backend = DockerSandboxBackend(client=mock_client)
        info = await backend.get_container("nonexistent")
        assert info is None

    @pytest.mark.asyncio
    async def test_list_containers(self) -> None:
        """Test listing containers by labels."""
        mock_containers = [
            _make_mock_container(container_id="c1", name="sandbox-1"),
            _make_mock_container(container_id="c2", name="sandbox-2"),
        ]
        mock_client = MagicMock()
        mock_client.containers.list.return_value = mock_containers

        backend = DockerSandboxBackend(client=mock_client)
        results = await backend.list_containers({"echomind.sandbox": "true"})

        assert len(results) == 2
        mock_client.containers.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_env_success(self) -> None:
        """Test injecting environment variables via tar archive."""
        mock_container = _make_mock_container()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        backend = DockerSandboxBackend(client=mock_client)
        await backend.inject_env("abc123", {"SESSION_ID": "test-session"})

        mock_container.put_archive.assert_called_once()
        # Verify the path is /tmp
        call_args = mock_container.put_archive.call_args
        assert call_args[0][0] == "/tmp"

    @pytest.mark.asyncio
    async def test_inject_env_not_found_raises(self) -> None:
        """Test injecting into nonexistent container raises RuntimeError."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("not found")

        backend = DockerSandboxBackend(client=mock_client)
        with pytest.raises(RuntimeError, match="not found for env injection"):
            await backend.inject_env("nonexistent", {"KEY": "val"})
