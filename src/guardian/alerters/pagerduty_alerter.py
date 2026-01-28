"""
PagerDuty alerter implementation.

Creates incidents via PagerDuty Events API v2.
"""

import logging
from typing import Any

import httpx

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails
from guardian.logic.exceptions import PagerDutyAlertError

logger = logging.getLogger("echomind-guardian")

# PagerDuty Events API v2 endpoint
PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


class PagerDutyAlerter(Alerter):
    """
    Alerter that creates PagerDuty incidents.

    Uses PagerDuty Events API v2 for delivery.
    """

    def __init__(
        self,
        routing_key: str,
        severity: str = "error",
        timeout: float = 10.0,
    ) -> None:
        """
        Initialize PagerDuty alerter.

        Args:
            routing_key: PagerDuty Events API v2 routing key.
            severity: Alert severity (critical, error, warning, info).
            timeout: Request timeout in seconds.
        """
        self._routing_key = routing_key
        self._severity = severity
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """
        Get the alerter name.

        Returns:
            Alerter name.
        """
        return "PagerDutyAlerter"

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client.

        Returns:
            Async HTTP client.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def send_alert(self, details: FailureDetails) -> None:
        """
        Send alert to PagerDuty.

        Args:
            details: Failure details from advisory.

        Raises:
            PagerDutyAlertError: If PagerDuty API call fails.
        """
        summary = AdvisoryParser.get_advisory_summary(details)

        payload = self._build_payload(details, summary)

        try:
            client = await self._get_client()
            response = await client.post(PAGERDUTY_EVENTS_URL, json=payload)
            response.raise_for_status()
            logger.debug("✅ PagerDuty alert sent for seq %d", details.stream_seq)

        except httpx.HTTPStatusError as e:
            raise PagerDutyAlertError(
                f"PagerDuty API returned {e.response.status_code}: {e.response.text}",
                retryable=e.response.status_code >= 500,
            ) from e
        except httpx.RequestError as e:
            raise PagerDutyAlertError(f"Request failed: {e}", retryable=True) from e

    def _build_payload(
        self,
        details: FailureDetails,
        summary: str,
    ) -> dict[str, Any]:
        """
        Build PagerDuty event payload.

        Args:
            details: Failure details.
            summary: Human-readable summary.

        Returns:
            PagerDuty Events API v2 payload.
        """
        # Create dedup key from stream, consumer, and sequence
        dedup_key = f"{details.stream}-{details.consumer}-{details.stream_seq}"

        # Build custom details
        custom_details: dict[str, Any] = {
            "stream": details.stream,
            "consumer": details.consumer,
            "stream_seq": details.stream_seq,
            "advisory_type": details.advisory_type,
        }

        if details.deliveries:
            custom_details["deliveries"] = details.deliveries

        if details.reason:
            custom_details["reason"] = details.reason

        if details.original_subject:
            custom_details["original_subject"] = details.original_subject

        return {
            "routing_key": self._routing_key,
            "dedup_key": dedup_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"[EchoMind DLQ] {summary}",
                "severity": self._severity,
                "source": "echomind-guardian",
                "component": details.consumer,
                "group": details.stream,
                "class": details.advisory_type,
                "custom_details": custom_details,
            },
        }

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
