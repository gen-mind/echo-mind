"""
Guardian error handling middleware.

Converts domain exceptions to appropriate responses.
"""

import logging
from typing import Any

from guardian.logic.exceptions import (
    AdvisoryParseError,
    AlerterError,
    GuardianError,
    RateLimitExceededError,
)

logger = logging.getLogger("echomind-guardian")


async def handle_guardian_error(error: GuardianError) -> dict[str, Any]:
    """
    Handle Guardian domain error.

    Args:
        error: The Guardian error.

    Returns:
        Dictionary with error info and whether to retry.
    """
    error_info: dict[str, Any] = {
        "error_type": type(error).__name__,
        "message": error.message,
        "retryable": error.retryable,
    }

    if isinstance(error, AdvisoryParseError):
        logger.warning("⚠️ Advisory parse error: %s", error.message)
        error_info["should_ack"] = True  # Don't retry unparseable messages

    elif isinstance(error, RateLimitExceededError):
        logger.debug("🚫 Rate limited: %s", error.subject)
        error_info["should_ack"] = True  # Don't retry rate limited
        error_info["subject"] = error.subject

    elif isinstance(error, AlerterError):
        logger.error("❌ Alerter error: %s", error.message)
        error_info["should_ack"] = True  # Still ack, alerter failure is non-fatal
        error_info["alerter"] = error.alerter_name

    else:
        logger.error("❌ Guardian error: %s", error.message)
        error_info["should_ack"] = not error.retryable

    return error_info
