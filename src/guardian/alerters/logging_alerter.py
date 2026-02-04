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
            f"💀 DLQ Alert | type={details.advisory_type} stream={details.stream} "
            f"consumer={details.consumer} seq={details.stream_seq} "
            f"deliveries={details.deliveries or 'N/A'} reason={details.reason or 'N/A'} "
            f"subject={details.original_subject or 'unknown'} | {summary}"
        )
