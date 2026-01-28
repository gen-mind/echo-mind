"""Unit tests for LoggingAlerter."""

import logging
from datetime import datetime, timezone

import pytest

from guardian.alerters.logging_alerter import LoggingAlerter
from guardian.logic.advisory_parser import FailureDetails


class TestLoggingAlerter:
    """Tests for LoggingAlerter."""

    def test_name(self) -> None:
        """Test alerter name property."""
        alerter = LoggingAlerter()
        assert alerter.name == "LoggingAlerter"

    @pytest.mark.asyncio
    async def test_send_alert_max_deliveries(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test send_alert logs max_deliveries advisory at CRITICAL level."""
        alerter = LoggingAlerter()
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

        with caplog.at_level(logging.CRITICAL, logger="echomind-guardian"):
            await alerter.send_alert(details)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.CRITICAL
        assert "DLQ Alert" in record.message
        assert "max_deliveries" in record.message
        assert "ECHOMIND" in record.message
        assert "12345" in record.message
        assert "5" in record.message

    @pytest.mark.asyncio
    async def test_send_alert_terminated(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test send_alert logs terminated advisory at CRITICAL level."""
        alerter = LoggingAlerter()
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

        with caplog.at_level(logging.CRITICAL, logger="echomind-guardian"):
            await alerter.send_alert(details)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "terminated" in record.message
        assert "Processing timeout" in record.message

    @pytest.mark.asyncio
    async def test_send_alert_with_none_values(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test send_alert handles None values gracefully."""
        alerter = LoggingAlerter()
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=100,
            deliveries=None,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject=None,
        )

        with caplog.at_level(logging.CRITICAL, logger="echomind-guardian"):
            await alerter.send_alert(details)

        assert len(caplog.records) == 1
        assert "N/A" in caplog.records[0].message or "unknown" in caplog.records[0].message

    @pytest.mark.asyncio
    async def test_send_alert_no_errors(self) -> None:
        """Test send_alert doesn't raise errors."""
        alerter = LoggingAlerter()
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="test.subject",
        )

        # Should not raise
        await alerter.send_alert(details)

    @pytest.mark.asyncio
    async def test_close_is_noop(self) -> None:
        """Test close method exists and is a no-op."""
        alerter = LoggingAlerter()
        # Should not raise
        await alerter.close()

    def test_multiple_instances(self) -> None:
        """Test multiple instances have same name."""
        alerter1 = LoggingAlerter()
        alerter2 = LoggingAlerter()
        assert alerter1.name == alerter2.name == "LoggingAlerter"
