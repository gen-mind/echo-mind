"""
Logging alerter implementation.

Logs failures to stdout at CRITICAL level.
"""

import logging

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails

logger = logging.getLogger("echomind-guardian")


class LoggingAlerter(Alerter):
    """
    Alerter that logs failures at CRITICAL level.

    This is the default alerter that requires no configuration.
    """

    @property
    def name(self) -> str:
        """
        Get the alerter name.

        Returns:
            Alerter name.
        """
        return "LoggingAlerter"

    async def send_alert(self, details: FailureDetails) -> None:
        """
        Log failure details at CRITICAL level.

        Args:
            details: Failure details from advisory.
        """
        summary = AdvisoryParser.get_advisory_summary(details)

        logger.critical(
            "💀 DLQ Alert | type=%s stream=%s consumer=%s seq=%d "
            "deliveries=%s reason=%s subject=%s | %s",
            details.advisory_type,
            details.stream,
            details.consumer,
            details.stream_seq,
            details.deliveries or "N/A",
            details.reason or "N/A",
            details.original_subject or "unknown",
            summary,
        )
