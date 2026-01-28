"""Unit tests for GuardianService."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from guardian.alerters.base import Alerter
from guardian.logic.advisory_parser import FailureDetails
from guardian.logic.exceptions import AlerterError
from guardian.logic.guardian_service import GuardianService
from guardian.logic.rate_limiter import RateLimiter


class MockAlerter(Alerter):
    """Mock alerter for testing."""

    def __init__(self, name: str = "MockAlerter") -> None:
        self._name = name
        self.alerts_sent: list[FailureDetails] = []
        self.should_fail = False
        self.fail_retryable = True
        self.closed = False

    @property
    def name(self) -> str:
        return self._name

    async def send_alert(self, details: FailureDetails) -> None:
        if self.should_fail:
            raise AlerterError(self._name, "Mock failure", retryable=self.fail_retryable)
        self.alerts_sent.append(details)

    async def close(self) -> None:
        self.closed = True


class TestGuardianService:
    """Tests for GuardianService."""

    def test_init(self) -> None:
        """Test service initialization."""
        alerters = [MockAlerter()]
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)

        service = GuardianService(alerters=alerters, rate_limiter=rate_limiter)

        assert service.advisories_processed == 0
        assert service.alerts_sent == 0
        assert service.alerts_rate_limited == 0
        assert service.alerts_failed == 0

    def test_properties(self) -> None:
        """Test service properties."""
        alerters = [MockAlerter()]
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)

        service = GuardianService(alerters=alerters, rate_limiter=rate_limiter)

        assert isinstance(service.advisories_processed, int)
        assert isinstance(service.alerts_sent, int)
        assert isinstance(service.alerts_rate_limited, int)
        assert isinstance(service.alerts_failed, int)

    @pytest.mark.asyncio
    async def test_process_advisory_success(self) -> None:
        """Test successful advisory processing."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "ingestor-consumer",
            "stream_seq": 12345,
            "deliveries": 5,
            "timestamp": "2025-01-15T10:30:00Z",
        }).encode()

        details = await service.process_advisory(advisory_data)

        assert details.advisory_type == "max_deliveries"
        assert details.stream_seq == 12345
        assert service.advisories_processed == 1
        assert service.alerts_sent == 1
        assert len(alerter.alerts_sent) == 1

    @pytest.mark.asyncio
    async def test_process_advisory_multiple_alerters(self) -> None:
        """Test advisory processing with multiple alerters."""
        alerter1 = MockAlerter("Alerter1")
        alerter2 = MockAlerter("Alerter2")
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter1, alerter2], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 100,
            "deliveries": 3,
        }).encode()

        await service.process_advisory(advisory_data)

        assert service.alerts_sent == 2
        assert len(alerter1.alerts_sent) == 1
        assert len(alerter2.alerts_sent) == 1

    @pytest.mark.asyncio
    async def test_process_advisory_rate_limited(self) -> None:
        """Test advisory processing with rate limiting."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=2, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "ingestor-consumer-document-process",
            "stream_seq": 1,
            "deliveries": 3,
        }).encode()

        # First two should be allowed
        await service.process_advisory(advisory_data)
        await service.process_advisory(advisory_data)

        # Third should be rate limited
        await service.process_advisory(advisory_data)

        assert service.advisories_processed == 3
        assert service.alerts_sent == 2
        assert service.alerts_rate_limited == 1
        assert len(alerter.alerts_sent) == 2

    @pytest.mark.asyncio
    async def test_process_advisory_alerter_failure(self) -> None:
        """Test advisory processing continues despite alerter failure."""
        alerter1 = MockAlerter("Alerter1")
        alerter1.should_fail = True
        alerter2 = MockAlerter("Alerter2")
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter1, alerter2], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 100,
            "deliveries": 3,
        }).encode()

        await service.process_advisory(advisory_data)

        assert service.advisories_processed == 1
        assert service.alerts_sent == 1  # Only alerter2 succeeded
        assert service.alerts_failed == 1  # alerter1 failed
        assert len(alerter2.alerts_sent) == 1

    @pytest.mark.asyncio
    async def test_process_advisory_unexpected_exception(self) -> None:
        """Test advisory processing handles unexpected exceptions."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        # Patch send_alert to raise unexpected exception
        with patch.object(alerter, "send_alert", side_effect=RuntimeError("Unexpected")):
            advisory_data = json.dumps({
                "type": "io.nats.jetstream.advisory.v1.max_deliver",
                "stream": "ECHOMIND",
                "consumer": "test-consumer",
                "stream_seq": 100,
                "deliveries": 3,
            }).encode()

            # Should not raise, but should count as failed
            await service.process_advisory(advisory_data)

        assert service.alerts_failed == 1

    @pytest.mark.asyncio
    async def test_process_advisory_different_subjects(self) -> None:
        """Test rate limiting is per-subject."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=1, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        # Different consumers = different subjects
        advisory1 = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "ingestor-consumer-document-process",
            "stream_seq": 1,
            "deliveries": 3,
        }).encode()

        advisory2 = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "connector-consumer-google-drive",
            "stream_seq": 2,
            "deliveries": 3,
        }).encode()

        await service.process_advisory(advisory1)
        await service.process_advisory(advisory2)

        # Both should succeed (different subjects)
        assert service.alerts_sent == 2
        assert service.alerts_rate_limited == 0

    @pytest.mark.asyncio
    async def test_process_advisory_terminated_type(self) -> None:
        """Test processing terminated advisory type."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.terminated",
            "stream": "ECHOMIND",
            "consumer": "connector-consumer",
            "stream_seq": 67890,
            "reason": "Processing timeout",
            "timestamp": "2025-01-15T11:00:00Z",
        }).encode()

        details = await service.process_advisory(advisory_data)

        assert details.advisory_type == "terminated"
        assert details.reason == "Processing timeout"
        assert service.alerts_sent == 1

    def test_get_stats(self) -> None:
        """Test get_stats returns correct statistics."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        stats = service.get_stats()

        assert "advisories_processed" in stats
        assert "alerts_sent" in stats
        assert "alerts_rate_limited" in stats
        assert "alerts_failed" in stats
        assert "rate_limiter" in stats
        assert stats["advisories_processed"] == 0
        assert stats["alerts_sent"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_after_processing(self) -> None:
        """Test get_stats after processing advisories."""
        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 1,
            "deliveries": 3,
        }).encode()

        await service.process_advisory(advisory_data)
        await service.process_advisory(advisory_data)

        stats = service.get_stats()

        assert stats["advisories_processed"] == 2
        assert stats["alerts_sent"] == 2

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test close method closes all alerters."""
        alerter1 = MockAlerter("Alerter1")
        alerter2 = MockAlerter("Alerter2")
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter1, alerter2], rate_limiter=rate_limiter)

        await service.close()

        assert alerter1.closed
        assert alerter2.closed

    @pytest.mark.asyncio
    async def test_close_continues_on_error(self) -> None:
        """Test close continues even if alerter close fails."""
        alerter1 = MockAlerter("Alerter1")
        alerter2 = MockAlerter("Alerter2")
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[alerter1, alerter2], rate_limiter=rate_limiter)

        # Make first alerter fail on close
        async def fail_close() -> None:
            raise RuntimeError("Close failed")

        alerter1.close = fail_close

        # Should not raise
        await service.close()

        # Second alerter should still be closed
        assert alerter2.closed

    @pytest.mark.asyncio
    async def test_no_alerters(self) -> None:
        """Test service with no alerters."""
        rate_limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        service = GuardianService(alerters=[], rate_limiter=rate_limiter)

        advisory_data = json.dumps({
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 1,
            "deliveries": 3,
        }).encode()

        details = await service.process_advisory(advisory_data)

        assert details.stream_seq == 1
        assert service.advisories_processed == 1
        assert service.alerts_sent == 0  # No alerters


class TestGuardianServiceConcurrency:
    """Tests for GuardianService concurrent behavior."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_advisories(self) -> None:
        """Test processing multiple advisories concurrently."""
        import asyncio

        alerter = MockAlerter()
        rate_limiter = RateLimiter(max_per_subject=100, window_seconds=60)
        service = GuardianService(alerters=[alerter], rate_limiter=rate_limiter)

        async def process_one(seq: int) -> None:
            advisory_data = json.dumps({
                "type": "io.nats.jetstream.advisory.v1.max_deliver",
                "stream": "ECHOMIND",
                "consumer": f"test-consumer-{seq % 10}",
                "stream_seq": seq,
                "deliveries": 3,
            }).encode()
            await service.process_advisory(advisory_data)

        # Process 20 advisories concurrently
        await asyncio.gather(*[process_one(i) for i in range(20)])

        assert service.advisories_processed == 20
        assert service.alerts_sent == 20
