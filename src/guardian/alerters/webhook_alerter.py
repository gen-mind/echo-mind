"""
Generic webhook alerter implementation.

Posts failure alerts to a configurable HTTP endpoint.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails
from guardian.logic.exceptions import WebhookAlertError

logger = logging.getLogger("echomind-guardian")


class WebhookAlerter(Alerter):
    """
    Alerter that posts failures to a generic webhook.

    Supports optional HMAC signing for payload verification.
    """

    def __init__(
        self,
        webhook_url: str,
        secret: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Initialize webhook alerter.

        Args:
            webhook_url: Webhook endpoint URL.
            secret: Optional HMAC secret for signing.
            timeout: Request timeout in seconds.
        """
        self._webhook_url = webhook_url
        self._secret = secret
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """
        Get the alerter name.

        Returns:
            Alerter name.
        """
        return "WebhookAlerter"

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
        Send alert to webhook.

        Args:
            details: Failure details from advisory.

        Raises:
            WebhookAlertError: If webhook call fails.
        """
        summary = AdvisoryParser.get_advisory_summary(details)

        payload = self._build_payload(details, summary)
        headers = self._build_headers(payload)

        try:
            client = await self._get_client()
            response = await client.post(
                self._webhook_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            logger.debug("✅ Webhook alert sent for seq %d", details.stream_seq)

        except httpx.HTTPStatusError as e:
            raise WebhookAlertError(
                f"Webhook returned {e.response.status_code}: {e.response.text}",
                retryable=e.response.status_code >= 500,
            ) from e
        except httpx.RequestError as e:
            raise WebhookAlertError(f"Request failed: {e}", retryable=True) from e

    def _build_payload(
        self,
        details: FailureDetails,
        summary: str,
    ) -> dict[str, Any]:
        """
        Build webhook payload.

        Args:
            details: Failure details.
            summary: Human-readable summary.

        Returns:
            Webhook payload.
        """
        return {
            "event": "dlq_alert",
            "source": "echomind-guardian",
            "summary": summary,
            "details": {
                "advisory_type": details.advisory_type,
                "stream": details.stream,
                "consumer": details.consumer,
                "stream_seq": details.stream_seq,
                "deliveries": details.deliveries,
                "reason": details.reason,
                "original_subject": details.original_subject,
                "timestamp": details.timestamp.isoformat(),
            },
        }

    def _build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Build request headers, including signature if secret is set.

        Args:
            payload: Request payload.

        Returns:
            Request headers.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "echomind-guardian/1.0",
        }

        if self._secret:
            # Create HMAC-SHA256 signature
            payload_bytes = json.dumps(payload, sort_keys=True).encode()
            signature = hmac.new(
                self._secret.encode(),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Signature-SHA256"] = signature

        return headers

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
