"""Unit tests for PagerDutyAlerter."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from guardian.alerters.pagerduty_alerter import PagerDutyAlerter, PAGERDUTY_EVENTS_URL
from guardian.logic.advisory_parser import FailureDetails
from guardian.logic.exceptions import PagerDutyAlertError


class TestPagerDutyAlerter:
    """Tests for PagerDutyAlerter."""

    def test_name(self) -> None:
        """Test alerter name property."""
        alerter = PagerDutyAlerter(routing_key="test-key")
        assert alerter.name == "PagerDutyAlerter"

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        alerter = PagerDutyAlerter(routing_key="test-routing-key")
        assert alerter._routing_key == "test-routing-key"
        assert alerter._severity == "error"
        assert alerter._timeout == 10.0

    def test_init_with_custom_severity(self) -> None:
        """Test initialization with custom severity."""
        alerter = PagerDutyAlerter(routing_key="test-key", severity="critical")
        assert alerter._severity == "critical"

    def test_init_with_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        alerter = PagerDutyAlerter(routing_key="test-key", timeout=30.0)
        assert alerter._timeout == 30.0

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self) -> None:
        """Test _get_client creates new client when none exists."""
        alerter = PagerDutyAlerter(routing_key="test-key")
        assert alerter._client is None

        client = await alerter._get_client()

        assert client is not None
        assert alerter._client is client
        await alerter.close()

    @pytest.mark.asyncio
    async def test_get_client_returns_existing(self) -> None:
        """Test _get_client returns existing client."""
        alerter = PagerDutyAlerter(routing_key="test-key")

        client1 = await alerter._get_client()
        client2 = await alerter._get_client()

        assert client1 is client2
        await alerter.close()

    @pytest.mark.asyncio
    async def test_send_alert_success(self) -> None:
        """Test send_alert with successful response."""
        alerter = PagerDutyAlerter(routing_key="test-routing-key")
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
            assert call_args[0][0] == PAGERDUTY_EVENTS_URL

    @pytest.mark.asyncio
    async def test_send_alert_http_error_retryable(self) -> None:
        """Test send_alert raises retryable error on 5xx."""
        alerter = PagerDutyAlerter(routing_key="test-key")
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
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(PagerDutyAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_send_alert_http_error_not_retryable(self) -> None:
        """Test send_alert raises non-retryable error on 4xx."""
        alerter = PagerDutyAlerter(routing_key="test-key")
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
        mock_response.text = "Invalid routing key"

        with patch.object(alerter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Client Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(PagerDutyAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_send_alert_request_error(self) -> None:
        """Test send_alert raises retryable error on request failure."""
        alerter = PagerDutyAlerter(routing_key="test-key")
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

            with pytest.raises(PagerDutyAlertError) as exc_info:
                await alerter.send_alert(details)

            assert exc_info.value.retryable is True

    def test_build_payload_structure(self) -> None:
        """Test _build_payload creates valid PagerDuty payload."""
        alerter = PagerDutyAlerter(routing_key="test-routing-key", severity="error")
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

        assert payload["routing_key"] == "test-routing-key"
        assert payload["event_action"] == "trigger"
        assert "dedup_key" in payload
        assert "payload" in payload

    def test_build_payload_dedup_key(self) -> None:
        """Test _build_payload creates correct dedup_key."""
        alerter = PagerDutyAlerter(routing_key="test-key")
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

        assert payload["dedup_key"] == "ECHOMIND-ingestor-consumer-12345"

    def test_build_payload_inner_payload(self) -> None:
        """Test _build_payload creates correct inner payload."""
        alerter = PagerDutyAlerter(routing_key="test-key", severity="critical")
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
        inner = payload["payload"]

        assert "[EchoMind DLQ]" in inner["summary"]
        assert inner["severity"] == "critical"
        assert inner["source"] == "echomind-guardian"
        assert inner["component"] == "ingestor-consumer"
        assert inner["group"] == "ECHOMIND"
        assert inner["class"] == "max_deliveries"

    def test_build_payload_custom_details(self) -> None:
        """Test _build_payload includes custom_details."""
        alerter = PagerDutyAlerter(routing_key="test-key")
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
        custom = payload["payload"]["custom_details"]

        assert custom["stream"] == "ECHOMIND"
        assert custom["consumer"] == "ingestor-consumer"
        assert custom["stream_seq"] == 12345
        assert custom["advisory_type"] == "max_deliveries"
        assert custom["deliveries"] == 5
        assert custom["original_subject"] == "document.process"

    def test_build_payload_terminated_with_reason(self) -> None:
        """Test _build_payload includes reason for terminated advisory."""
        alerter = PagerDutyAlerter(routing_key="test-key")
        details = FailureDetails(
            advisory_type="terminated",
            stream="ECHOMIND",
            consumer="connector-consumer",
            stream_seq=67890,
            deliveries=None,
            reason="Processing timeout",
            timestamp=datetime.now(timezone.utc),
            original_subject="connector.sync",
        )

        payload = alerter._build_payload(details, "Test summary")
        custom = payload["payload"]["custom_details"]

        assert custom["reason"] == "Processing timeout"
        assert "deliveries" not in custom

    def test_build_payload_without_optional_fields(self) -> None:
        """Test _build_payload excludes None optional fields."""
        alerter = PagerDutyAlerter(routing_key="test-key")
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=None,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject=None,
        )

        payload = alerter._build_payload(details, "Test summary")
        custom = payload["payload"]["custom_details"]

        assert "deliveries" not in custom
        assert "reason" not in custom
        assert "original_subject" not in custom

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Test close method closes the HTTP client."""
        alerter = PagerDutyAlerter(routing_key="test-key")

        client = await alerter._get_client()
        assert alerter._client is not None

        with patch.object(client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await alerter.close()
            mock_aclose.assert_called_once()

        assert alerter._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self) -> None:
        """Test close when no client exists doesn't error."""
        alerter = PagerDutyAlerter(routing_key="test-key")
        assert alerter._client is None

        await alerter.close()


class TestPagerDutyEventsUrl:
    """Tests for PagerDuty Events URL constant."""

    def test_events_url_correct(self) -> None:
        """Test PAGERDUTY_EVENTS_URL is correct."""
        assert PAGERDUTY_EVENTS_URL == "https://events.pagerduty.com/v2/enqueue"
