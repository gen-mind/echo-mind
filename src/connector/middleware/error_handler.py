"""
Error handling middleware for the Connector Service.

Converts domain exceptions to appropriate responses.
"""

import logging
from typing import Any, Callable, Coroutine

from connector.logic.exceptions import (
    AuthenticationError,
    CheckpointError,
    ConnectorError,
    DatabaseError,
    DownloadError,
    ExportError,
    FileTooLargeError,
    MinioUploadError,
    ProviderError,
    ProviderNotFoundError,
    RateLimitError,
)

logger = logging.getLogger("echomind-connector.error_handler")


async def handle_connector_error(
    error: ConnectorError,
    connector_id: int | None = None,
) -> dict[str, Any]:
    """
    Handle connector errors and return structured error info.

    Args:
        error: The connector error.
        connector_id: Optional connector ID for context.

    Returns:
        Dictionary with error details.
    """
    error_info: dict[str, Any] = {
        "error_type": type(error).__name__,
        "message": str(error),
        "connector_id": connector_id,
        "should_retry": False,
        "retry_after": None,
    }

    if isinstance(error, AuthenticationError):
        logger.error(
            f"❌ Authentication failed for {error.provider}: {error.reason}"
        )
        error_info["should_retry"] = False  # Need manual intervention

    elif isinstance(error, RateLimitError):
        logger.warning(
            f"⚠️ Rate limit hit for {error.provider}, retry after {error.retry_after} seconds"
        )
        error_info["should_retry"] = True
        error_info["retry_after"] = error.retry_after or 60

    elif isinstance(error, FileTooLargeError):
        logger.warning(
            f"⚠️ File {error.file_id} too large: {error.size} > {error.limit} bytes"
        )
        error_info["should_retry"] = False  # Skip this file

    elif isinstance(error, (DownloadError, ExportError)):
        logger.error(
            f"❌ Download/export error for {error.file_id}: {error.reason}"
        )
        error_info["should_retry"] = True  # Transient, can retry

    elif isinstance(error, MinioUploadError):
        logger.error(
            f"❌ MinIO upload failed for {error.object_name}: {error.reason}"
        )
        error_info["should_retry"] = True

    elif isinstance(error, DatabaseError):
        logger.error(
            f"❌ Database error in {error.operation}: {error.reason}"
        )
        error_info["should_retry"] = True

    elif isinstance(error, CheckpointError):
        logger.error(
            f"❌ Checkpoint error for connector {error.connector_id}: {error.reason}"
        )
        error_info["should_retry"] = False

    elif isinstance(error, ProviderNotFoundError):
        logger.error(f"❌ Unsupported provider: {error.provider_type}")
        error_info["should_retry"] = False

    elif isinstance(error, ProviderError):
        logger.error(
            f"❌ Provider error from {error.provider}: {error.message}"
        )
        error_info["should_retry"] = True

    else:
        logger.error(f"❌ Connector error: {error.message}")
        error_info["should_retry"] = True

    return error_info


def with_error_handling(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """
    Decorator that wraps async functions with error handling.

    Args:
        func: Async function to wrap.

    Returns:
        Wrapped function with error handling.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ConnectorError as e:
            error_info = await handle_connector_error(e)
            if error_info["should_retry"]:
                raise  # Let caller handle retry
            return None
        except Exception as e:
            logger.exception(f"❌ Unexpected error in {func.__name__}: {e}")
            raise

    return wrapper
