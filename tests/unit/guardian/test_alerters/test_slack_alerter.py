"""Unit tests for SlackAlerter."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from guardian.alerters.slack_alerter import SlackAlerter
from guardian.logic.advisory_parser import FailureDetails
from guardian.logic.exceptions import SlackAlertError


class TestSlackAlerter:
    """Tests for SlackAlerter."""

    def test_name(self) -> None:
        """Test alerter name property."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        assert alerter.name == "SlackAlerter"

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        assert alerter._webhook_url == "https://hooks.slack.com/test"
        assert alerter._channel is None
        assert alerter._timeout == 10.0

    def test_init_with_channel(self) -> None:
        """Test initialization with channel override."""
        alerter = SlackAlerter(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
        )
        assert alerter._channel == "#alerts"

    def test_init_with_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        alerter = SlackAlerter(
            webhook_url="https://hooks.slack.com/test",
            timeout=30.0,
        )
        assert alerter._timeout == 30.0

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self) -> None:
        """Test _get_client creates new client when none exists."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        assert alerter._client is None

        client = await alerter._get_client()

        assert client is not None
        assert alerter._client is client
        await alerter.close()

    @pytest.mark.asyncio
    async def test_get_client_returns_existing(self) -> None:
        """Test _get_client returns existing client."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")

        client1 = await alerter._get_client()
        client2 = await alerter._get_client()

        assert client1 is client2
        await alerter.close()

    @pytest.mark.asyncio
    async def test_send_alert_success(self) -> None:
        """Test send_alert with successful response."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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
            assert call_args[0][0] == "https://hooks.slack.com/test"
            assert "json" in call_args[1]

    @pytest.mark.asyncio
    async def test_send_alert_http_error_retryable(self) -> None:
        """Test send_alert raises retryable error on 5xx."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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

            with pytest.raises(SlackAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_send_alert_http_error_not_retryable(self) -> None:
        """Test send_alert raises non-retryable error on 4xx."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Client Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(SlackAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_send_alert_request_error(self) -> None:
        """Test send_alert raises retryable error on request failure."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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

            with pytest.raises(SlackAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    def test_build_payload_max_deliveries(self) -> None:
        """Test _build_payload for max_deliveries advisory."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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

        assert "text" in payload
        assert ":rotating_light:" in payload["text"]
        assert "DLQ Alert" in payload["text"]
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["color"] == "danger"

    def test_build_payload_terminated(self) -> None:
        """Test _build_payload for terminated advisory."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        details = FailureDetails(
            advisory_type="terminated",
            stream="ECHOMIND",
            consumer="connector-consumer",
            stream_seq=67890,
            deliveries=None,
            reason="timeout",
            timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            original_subject="connector.sync",
        )

        payload = alerter._build_payload(details, "Test summary")

        assert ":skull:" in payload["text"]

    def test_build_payload_with_channel(self) -> None:
        """Test _build_payload includes channel when set."""
        alerter = SlackAlerter(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
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

        payload = alerter._build_payload(details, "Test summary")

        assert payload["channel"] == "#alerts"

    def test_build_payload_without_channel(self) -> None:
        """Test _build_payload doesn't include channel when not set."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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

        payload = alerter._build_payload(details, "Test summary")

        assert "channel" not in payload

    def test_build_payload_fields(self) -> None:
        """Test _build_payload includes all relevant fields."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
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

        payload = alerter._build_payload(details, "Test summary")
        fields = payload["attachments"][0]["fields"]

        field_titles = [f["title"] for f in fields]
        assert "Stream" in field_titles
        assert "Consumer" in field_titles
        assert "Sequence" in field_titles
        assert "Type" in field_titles
        assert "Deliveries" in field_titles
        assert "Subject" in field_titles

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Test close method closes the HTTP client."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")

        # Create a client
        client = await alerter._get_client()
        assert alerter._client is not None

        # Close should set client to None
        with patch.object(client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await alerter.close()
            mock_aclose.assert_called_once()

        assert alerter._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self) -> None:
        """Test close when no client exists doesn't error."""
        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        assert alerter._client is None

        # Should not raise
        await alerter.close()
