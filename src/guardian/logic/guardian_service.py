"""
Guardian service business logic.

Orchestrates advisory processing and alert routing.
"""

import logging
from typing import Any

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails
from guardian.logic.exceptions import AlerterError, GuardianError
from guardian.logic.rate_limiter import RateLimiter

logger = logging.getLogger("echomind-guardian")


class GuardianService:
    """
    Main Guardian service class.

    Processes NATS advisories and routes to configured alerters.
    """

    def __init__(
        self,
        alerters: list[Alerter],
        rate_limiter: RateLimiter,
    ) -> None:
        """
        Initialize Guardian service.

        Args:
            alerters: List of configured alerters.
            rate_limiter: Rate limiter instance.
        """
        self._alerters = alerters
        self._rate_limiter = rate_limiter

        # Statistics
        self._advisories_processed = 0
        self._alerts_sent = 0
        self._alerts_rate_limited = 0
        self._alerts_failed = 0

    @property
    def advisories_processed(self) -> int:
        """Get total advisories processed."""
        return self._advisories_processed

    @property
    def alerts_sent(self) -> int:
        """Get total alerts sent successfully."""
        return self._alerts_sent

    @property
    def alerts_rate_limited(self) -> int:
        """Get total alerts skipped due to rate limiting."""
        return self._alerts_rate_limited

    @property
    def alerts_failed(self) -> int:
        """Get total alerts that failed to send."""
        return self._alerts_failed

    async def process_advisory(self, data: bytes) -> FailureDetails:
        """
        Process a NATS advisory message.

        Parses the advisory, checks rate limits, and sends alerts.

        Args:
            data: Raw advisory message bytes.

        Returns:
            Parsed failure details.

        Raises:
            GuardianError: If processing fails critically.
        """
        # Parse advisory
        details = AdvisoryParser.parse(data)
        self._advisories_processed += 1

        logger.info(
            f"📥 Processing advisory: type={details.advisory_type} stream={details.stream} "
            f"consumer={details.consumer} seq={details.stream_seq}"
        )

        # Check rate limit
        if not self._rate_limiter.allow(details.original_subject):
            self._alerts_rate_limited += 1
            logger.warning(
                f"🚫 Rate limited alert for subject: {details.original_subject} (seq={details.stream_seq})"
            )
            return details

        # Send to all alerters
        await self._send_alerts(details)

        return details

    async def _send_alerts(self, details: FailureDetails) -> None:
        """
        Send alerts to all configured alerters.

        Continues with other alerters if one fails.

        Args:
            details: Failure details to send.
        """
        for alerter in self._alerters:
            try:
                await alerter.send_alert(details)
                self._alerts_sent += 1
                logger.debug(
                    f"✅ Alert sent via {alerter.name} for seq {details.stream_seq}"
                )
            except AlerterError as e:
                self._alerts_failed += 1
                logger.error(
                    f"❌ Alerter {alerter.name} failed for seq {details.stream_seq}: {e.message}"
                )
            except Exception as e:
                self._alerts_failed += 1
                logger.exception(
                    f"💀 Unexpected error in alerter {alerter.name} for seq {details.stream_seq}: {e}"
                )

    def get_stats(self) -> dict[str, Any]:
        """
        Get service statistics.

        Returns:
            Dictionary of statistics.
        """
        return {
            "advisories_processed": self._advisories_processed,
            "alerts_sent": self._alerts_sent,
            "alerts_rate_limited": self._alerts_rate_limited,
            "alerts_failed": self._alerts_failed,
            "rate_limiter": self._rate_limiter.get_stats(),
        }

    async def close(self) -> None:
        """Close all alerters."""
        for alerter in self._alerters:
            try:
                await alerter.close()
            except Exception as e:
                logger.warning(f"⚠️ Error closing alerter {alerter.name}: {e}")
