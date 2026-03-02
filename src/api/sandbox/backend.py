"""
Abstract backend interface for sandbox container operations.

Provides a protocol-agnostic interface that can be implemented
by different container runtimes (Docker, Kubernetes, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from api.sandbox.models import ContainerInfo


class SandboxBackend(ABC):
    """Abstract interface for sandbox container operations.

    Implementations must handle all container lifecycle operations.
    All methods are async to support both blocking (Docker SDK) and
    native async (Kubernetes) backends.
    """

    @abstractmethod
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
        """Create a new sandbox container without starting it.

        Args:
            name: Container name.
            image: Docker image to use.
            env: Environment variables to set.
            network: Docker network to attach.
            cpu_limit: CPU core limit (e.g., 2.0).
            memory_limit: Memory limit string (e.g., "2g").
            labels: Optional container labels.

        Returns:
            ContainerInfo with the created container details.

        Raises:
            RuntimeError: If container creation fails.
        """

    @abstractmethod
    async def start_container(self, container_id: str) -> None:
        """Start a stopped container.

        Args:
            container_id: Docker container ID.

        Raises:
            RuntimeError: If container start fails.
        """

    @abstractmethod
    async def stop_container(self, container_id: str, timeout: int = 5) -> None:
        """Stop a running container.

        Args:
            container_id: Docker container ID.
            timeout: Seconds to wait before force-killing.

        Raises:
            RuntimeError: If container stop fails.
        """

    @abstractmethod
    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container.

        Args:
            container_id: Docker container ID.
            force: Force removal even if running.

        Raises:
            RuntimeError: If container removal fails.
        """

    @abstractmethod
    async def get_container(self, container_id: str) -> ContainerInfo | None:
        """Get container info by ID.

        Args:
            container_id: Docker container ID.

        Returns:
            ContainerInfo if found, None otherwise.
        """

    @abstractmethod
    async def list_containers(
        self, labels: dict[str, str]
    ) -> list[ContainerInfo]:
        """List containers matching label filters.

        Args:
            labels: Label key-value pairs to filter by.

        Returns:
            List of matching ContainerInfo objects.
        """

    @abstractmethod
    async def inject_env(self, container_id: str, env: dict[str, str]) -> None:
        """Inject environment variables into a running container.

        For Docker, this is implemented by writing a .env file into the
        container's tmpfs mount, since Docker doesn't support runtime
        env injection natively.

        Args:
            container_id: Docker container ID.
            env: Environment variables to inject.

        Raises:
            RuntimeError: If env injection fails.
        """
