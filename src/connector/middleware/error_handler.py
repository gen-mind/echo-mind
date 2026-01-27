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
            "❌ Authentication failed for %s: %s",
            error.provider,
            error.reason,
        )
        error_info["should_retry"] = False  # Need manual intervention

    elif isinstance(error, RateLimitError):
        logger.warning(
            "⚠️ Rate limit hit for %s, retry after %s seconds",
            error.provider,
            error.retry_after,
        )
        error_info["should_retry"] = True
        error_info["retry_after"] = error.retry_after or 60

    elif isinstance(error, FileTooLargeError):
        logger.warning(
            "⚠️ File %s too large: %d > %d bytes",
            error.file_id,
            error.size,
            error.limit,
        )
        error_info["should_retry"] = False  # Skip this file

    elif isinstance(error, (DownloadError, ExportError)):
        logger.error(
            "❌ Download/export error for %s: %s",
            error.file_id,
            error.reason,
        )
        error_info["should_retry"] = True  # Transient, can retry

    elif isinstance(error, MinioUploadError):
        logger.error(
            "❌ MinIO upload failed for %s: %s",
            error.object_name,
            error.reason,
        )
        error_info["should_retry"] = True

    elif isinstance(error, DatabaseError):
        logger.error(
            "❌ Database error in %s: %s",
            error.operation,
            error.reason,
        )
        error_info["should_retry"] = True

    elif isinstance(error, CheckpointError):
        logger.error(
            "❌ Checkpoint error for connector %d: %s",
            error.connector_id,
            error.reason,
        )
        error_info["should_retry"] = False

    elif isinstance(error, ProviderNotFoundError):
        logger.error("❌ Unsupported provider: %s", error.provider_type)
        error_info["should_retry"] = False

    elif isinstance(error, ProviderError):
        logger.error(
            "❌ Provider error from %s: %s",
            error.provider,
            error.message,
        )
        error_info["should_retry"] = True

    else:
        logger.error("❌ Connector error: %s", error.message)
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
            logger.exception("❌ Unexpected error in %s: %s", func.__name__, e)
            raise

    return wrapper
