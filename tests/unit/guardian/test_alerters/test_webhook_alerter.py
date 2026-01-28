"""Unit tests for WebhookAlerter."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from guardian.alerters.webhook_alerter import WebhookAlerter
from guardian.logic.advisory_parser import FailureDetails
from guardian.logic.exceptions import WebhookAlertError


class TestWebhookAlerter:
    """Tests for WebhookAlerter."""

    def test_name(self) -> None:
        """Test alerter name property."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        assert alerter.name == "WebhookAlerter"

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        assert alerter._webhook_url == "https://example.com/webhook"
        assert alerter._secret is None
        assert alerter._timeout == 10.0

    def test_init_with_secret(self) -> None:
        """Test initialization with HMAC secret."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            secret="my-secret-key",
        )
        assert alerter._secret == "my-secret-key"

    def test_init_with_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            timeout=30.0,
        )
        assert alerter._timeout == 30.0

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self) -> None:
        """Test _get_client creates new client when none exists."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        assert alerter._client is None

        client = await alerter._get_client()

        assert client is not None
        assert alerter._client is client
        await alerter.close()

    @pytest.mark.asyncio
    async def test_get_client_returns_existing(self) -> None:
        """Test _get_client returns existing client."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")

        client1 = await alerter._get_client()
        client2 = await alerter._get_client()

        assert client1 is client2
        await alerter.close()

    @pytest.mark.asyncio
    async def test_send_alert_success(self) -> None:
        """Test send_alert with successful response."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="ingestor-consumer",
            stream_seq=12345,
            deliveries=5,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="document.process",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            await alerter.send_alert(details)

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_send_alert_http_error_retryable(self) -> None:
        """Test send_alert raises retryable error on 5xx."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(WebhookAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_send_alert_http_error_not_retryable(self) -> None:
        """Test send_alert raises non-retryable error on 4xx."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Client Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(WebhookAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_send_alert_request_error(self) -> None:
        """Test send_alert raises retryable error on request failure."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="test",
        )

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(WebhookAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    def test_build_payload_structure(self) -> None:
        """Test _build_payload creates valid webhook payload."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="ingestor-consumer",
            stream_seq=12345,
            deliveries=5,
            reason=None,
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            original_subject="document.process",
        )

        payload = alerter._build_payload(details, "Test summary")

        assert payload["event"] == "dlq_alert"
        assert payload["source"] == "echomind-guardian"
        assert payload["summary"] == "Test summary"
        assert "details" in payload

    def test_build_payload_details(self) -> None:
        """Test _build_payload includes all details."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="ingestor-consumer",
            stream_seq=12345,
            deliveries=5,
            reason=None,
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            original_subject="document.process",
        )

        payload = alerter._build_payload(details, "Test summary")
        inner = payload["details"]

        assert inner["advisory_type"] == "max_deliveries"
        assert inner["stream"] == "ECHOMIND"
        assert inner["consumer"] == "ingestor-consumer"
        assert inner["stream_seq"] == 12345
        assert inner["deliveries"] == 5
        assert inner["reason"] is None
        assert inner["original_subject"] == "document.process"
        assert inner["timestamp"] == "2025-01-15T10:30:00+00:00"

    def test_build_headers_without_secret(self) -> None:
        """Test _build_headers without secret."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        payload = {"event": "test"}

        headers = alerter._build_headers(payload)

        assert headers["Content-Type"] == "application/json"
        assert headers["User-Agent"] == "echomind-guardian/1.0"
        assert "X-Signature-SHA256" not in headers

    def test_build_headers_with_secret(self) -> None:
        """Test _build_headers with HMAC secret."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            secret="my-secret-key",
        )
        payload = {"event": "test", "data": "value"}

        headers = alerter._build_headers(payload)

        assert "X-Signature-SHA256" in headers

        # Verify signature is correct
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        expected_signature = hmac.new(
            b"my-secret-key",
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Signature-SHA256"] == expected_signature

    def test_build_headers_signature_deterministic(self) -> None:
        """Test HMAC signature is deterministic for same payload."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            secret="test-secret",
        )
        payload = {"z": 1, "a": 2, "m": 3}

        headers1 = alerter._build_headers(payload)
        headers2 = alerter._build_headers(payload)

        assert headers1["X-Signature-SHA256"] == headers2["X-Signature-SHA256"]

    def test_build_headers_signature_different_for_different_payload(self) -> None:
        """Test HMAC signature differs for different payloads."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            secret="test-secret",
        )

        headers1 = alerter._build_headers({"data": "value1"})
        headers2 = alerter._build_headers({"data": "value2"})

        assert headers1["X-Signature-SHA256"] != headers2["X-Signature-SHA256"]

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Test close method closes the HTTP client."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")

        client = await alerter._get_client()
        assert alerter._client is not None

        with patch.object(client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await alerter.close()
            mock_aclose.assert_called_once()

        assert alerter._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self) -> None:
        """Test close when no client exists doesn't error."""
        alerter = WebhookAlerter(webhook_url="https://example.com/webhook")
        assert alerter._client is None

        await alerter.close()

    @pytest.mark.asyncio
    async def test_send_alert_includes_correct_headers(self) -> None:
        """Test send_alert includes correct headers in request."""
        alerter = WebhookAlerter(
            webhook_url="https://example.com/webhook",
            secret="test-secret",
        )
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="test",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            await alerter.send_alert(details)

            call_args = mock_client.post.call_args
            headers = call_args[1]["headers"]
            assert "X-Signature-SHA256" in headers
            assert headers["Content-Type"] == "application/json"
