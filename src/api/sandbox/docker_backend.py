"""
Docker implementation of the SandboxBackend interface.

Uses the Docker SDK for Python (docker-py) to manage containers.
All blocking Docker SDK calls are wrapped in asyncio.to_thread()
to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import docker
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from api.sandbox.backend import SandboxBackend
from api.sandbox.models import ContainerInfo

logger = logging.getLogger("echomind-sandbox")


class DockerSandboxBackend(SandboxBackend):
    """Docker SDK implementation of SandboxBackend.

    Wraps the synchronous Docker SDK in asyncio.to_thread() calls
    to prevent blocking the FastAPI event loop.
    """

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        """Initialize Docker backend.

        Args:
            client: Optional pre-configured Docker client. If None,
                    creates one from environment (DOCKER_HOST or socket).
        """
        # NOTE: docker-py DockerClient is not guaranteed thread-safe (docker-py#3229).
        # Under high concurrency, multiple asyncio.to_thread() calls sharing this
        # client could race on the underlying HTTP session. Practical risk is LOW
        # because Docker socket operations are short-lived and serialized by the GIL.
        self._client = client or docker.from_env()

    def _container_to_info(self, container: Container) -> ContainerInfo:
        """Convert Docker SDK Container to ContainerInfo.

        Args:
            container: Docker SDK container object.

        Returns:
            ContainerInfo with container details.
        """
        return ContainerInfo(
            container_id=container.id,
            name=container.name or "",
            status=container.status or "unknown",
            labels=container.labels or {},
        )

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
        """Create a sandbox container with security constraints.

        Args:
            name: Container name.
            image: Docker image to use.
            env: Environment variables to set.
            network: Docker network to attach.
            cpu_limit: CPU core limit.
            memory_limit: Memory limit string.
            labels: Optional container labels.

        Returns:
            ContainerInfo with the created container details.

        Raises:
            RuntimeError: If container creation fails.
        """
        all_labels = {"echomind.sandbox": "true", "echomind.managed": "true"}
        if labels:
            all_labels.update(labels)

        env_list = [f"{k}={v}" for k, v in env.items()]

        # Convert CPU limit to nano CPUs (Docker API format)
        nano_cpus = int(cpu_limit * 1e9)

        def _create() -> Container:
            return self._client.containers.create(
                image=image,
                name=name,
                environment=env_list,
                network=network,
                labels=all_labels,
                detach=True,
                # Security: run as non-root user
                user="1000",
                # Security: no privilege escalation
                security_opt=["no-new-privileges"],
                # Security: drop all capabilities
                cap_drop=["ALL"],
                # Security: read-only root filesystem
                read_only=True,
                # Writable tmpfs for temp files
                tmpfs={"/tmp": "size=100M,noexec,nosuid,nodev"},
                # Resource limits
                nano_cpus=nano_cpus,
                mem_limit=memory_limit,
                # Disable swap
                memswap_limit=memory_limit,
                # PID limit
                pids_limit=100,
            )

        try:
            container = await asyncio.to_thread(_create)
            logger.info(f"📦 Created container {name} ({container.short_id})")
            return self._container_to_info(container)
        except Exception as e:
            raise RuntimeError(f"Failed to create container {name}: {e}") from e

    async def start_container(self, container_id: str) -> None:
        """Start a stopped container.

        Args:
            container_id: Docker container ID.

        Raises:
            RuntimeError: If container start fails.
        """
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            await asyncio.to_thread(container.start)
            logger.info(f"▶️ Started container {container_id[:12]}")
        except NotFound as e:
            raise RuntimeError(f"Container {container_id[:12]} not found") from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to start container {container_id[:12]}: {e}"
            ) from e

    async def stop_container(self, container_id: str, timeout: int = 5) -> None:
        """Stop a running container.

        Args:
            container_id: Docker container ID.
            timeout: Seconds to wait before force-killing.

        Raises:
            RuntimeError: If container stop fails.
        """
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            await asyncio.to_thread(container.stop, timeout=timeout)
            logger.info(f"⏹️ Stopped container {container_id[:12]}")
        except NotFound:
            logger.warning(f"⚠️ Container {container_id[:12]} not found (already removed?)")
        except Exception as e:
            raise RuntimeError(
                f"Failed to stop container {container_id[:12]}: {e}"
            ) from e

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container.

        Args:
            container_id: Docker container ID.
            force: Force removal even if running.

        Raises:
            RuntimeError: If container removal fails.
        """
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            await asyncio.to_thread(container.remove, force=force)
            logger.info(f"🗑️ Removed container {container_id[:12]}")
        except NotFound:
            logger.warning(f"⚠️ Container {container_id[:12]} not found (already removed?)")
        except Exception as e:
            raise RuntimeError(
                f"Failed to remove container {container_id[:12]}: {e}"
            ) from e

    async def get_container(self, container_id: str) -> ContainerInfo | None:
        """Get container info by ID.

        Args:
            container_id: Docker container ID.

        Returns:
            ContainerInfo if found, None otherwise.
        """
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            return self._container_to_info(container)
        except NotFound:
            return None
        except Exception as e:
            logger.warning(f"⚠️ Failed to get container {container_id[:12]}: {e}")
            return None

    async def list_containers(
        self, labels: dict[str, str]
    ) -> list[ContainerInfo]:
        """List containers matching label filters.

        Args:
            labels: Label key-value pairs to filter by.

        Returns:
            List of matching ContainerInfo objects.
        """
        filters: dict[str, Any] = {
            "label": [f"{k}={v}" for k, v in labels.items()],
        }

        try:
            containers = await asyncio.to_thread(
                self._client.containers.list, all=True, filters=filters
            )
            return [self._container_to_info(c) for c in containers]
        except Exception as e:
            logger.warning(f"⚠️ Failed to list containers: {e}")
            return []

    async def inject_env(self, container_id: str, env: dict[str, str]) -> None:
        """Inject environment variables via a .env file in tmpfs.

        Docker doesn't support runtime env injection, so we write a
        .env file to the container's /tmp mount. The sandbox runner
        reads this file on startup or via inotify.

        Args:
            container_id: Docker container ID.
            env: Environment variables to inject.

        Raises:
            RuntimeError: If env injection fails.
        """
        env_content = "\n".join(f"{k}={v}" for k, v in env.items()) + "\n"
        env_bytes = env_content.encode("utf-8")

        import io
        import tarfile

        # Create a tar archive with the .env file
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="sandbox.env")
            info.size = len(env_bytes)
            tar.addfile(info, io.BytesIO(env_bytes))
        tar_stream.seek(0)

        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            await asyncio.to_thread(
                container.put_archive, "/tmp", tar_stream.getvalue()
            )
            logger.info(f"💉 Injected env into container {container_id[:12]}")
        except NotFound as e:
            raise RuntimeError(
                f"Container {container_id[:12]} not found for env injection"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to inject env into container {container_id[:12]}: {e}"
            ) from e
