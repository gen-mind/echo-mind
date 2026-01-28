"""
Slack alerter implementation.

Posts failure alerts to Slack via incoming webhook.
"""

import logging
from typing import Any

import httpx

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails
from guardian.logic.exceptions import SlackAlertError

logger = logging.getLogger("echomind-guardian")


class SlackAlerter(Alerter):
    """
    Alerter that posts failures to Slack.

    Uses Slack incoming webhooks for delivery.
    """

    def __init__(
        self,
        webhook_url: str,
        channel: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Initialize Slack alerter.

        Args:
            webhook_url: Slack incoming webhook URL.
            channel: Optional channel override.
            timeout: Request timeout in seconds.
        """
        self._webhook_url = webhook_url
        self._channel = channel
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """
        Get the alerter name.

        Returns:
            Alerter name.
        """
        return "SlackAlerter"

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
        Send alert to Slack.

        Args:
            details: Failure details from advisory.

        Raises:
            SlackAlertError: If Slack API call fails.
        """
        summary = AdvisoryParser.get_advisory_summary(details)

        payload = self._build_payload(details, summary)

        try:
            client = await self._get_client()
            response = await client.post(self._webhook_url, json=payload)
            response.raise_for_status()
            logger.debug("✅ Slack alert sent for seq %d", details.stream_seq)

        except httpx.HTTPStatusError as e:
            raise SlackAlertError(
                f"Slack API returned {e.response.status_code}: {e.response.text}",
                retryable=e.response.status_code >= 500,
            ) from e
        except httpx.RequestError as e:
            raise SlackAlertError(f"Request failed: {e}", retryable=True) from e

    def _build_payload(
        self,
        details: FailureDetails,
        summary: str,
    ) -> dict[str, Any]:
        """
        Build Slack message payload.

        Args:
            details: Failure details.
            summary: Human-readable summary.

        Returns:
            Slack message payload.
        """
        # Determine emoji based on advisory type
        emoji = ":rotating_light:" if details.advisory_type == "max_deliveries" else ":skull:"

        # Build fields
        fields = [
            {"title": "Stream", "value": details.stream, "short": True},
            {"title": "Consumer", "value": details.consumer, "short": True},
            {"title": "Sequence", "value": str(details.stream_seq), "short": True},
            {"title": "Type", "value": details.advisory_type, "short": True},
        ]

        if details.deliveries:
            fields.append({
                "title": "Deliveries",
                "value": str(details.deliveries),
                "short": True,
            })

        if details.reason:
            fields.append({
                "title": "Reason",
                "value": details.reason,
                "short": False,
            })

        if details.original_subject:
            fields.append({
                "title": "Subject",
                "value": details.original_subject,
                "short": True,
            })

        payload: dict[str, Any] = {
            "text": f"{emoji} *DLQ Alert*: {summary}",
            "attachments": [{
                "color": "danger",
                "fields": fields,
                "ts": str(int(details.timestamp.timestamp())),
            }],
        }

        if self._channel:
            payload["channel"] = self._channel

        return payload

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
