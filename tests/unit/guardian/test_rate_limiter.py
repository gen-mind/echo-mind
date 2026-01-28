"""Unit tests for alert rate limiter."""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from guardian.logic.rate_limiter import RateLimiter, RateLimitEntry


class TestRateLimitEntry:
    """Tests for RateLimitEntry dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        entry = RateLimitEntry()
        assert entry.count == 0
        assert isinstance(entry.window_start, float)

    def test_custom_values(self) -> None:
        """Test custom values."""
        entry = RateLimitEntry(count=5, window_start=1000.0)
        assert entry.count == 5
        assert entry.window_start == 1000.0


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_init(self) -> None:
        """Test initialization."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        assert limiter.max_per_subject == 5
        assert limiter.window_seconds == 60

    def test_allow_first_request(self) -> None:
        """Test first request is always allowed."""
        limiter = RateLimiter(max_per_subject=3, window_seconds=60)
        assert limiter.allow("test.subject") is True

    def test_allow_within_limit(self) -> None:
        """Test requests within limit are allowed."""
        limiter = RateLimiter(max_per_subject=3, window_seconds=60)

        assert limiter.allow("test.subject") is True
        assert limiter.allow("test.subject") is True
        assert limiter.allow("test.subject") is True

    def test_allow_exceeds_limit(self) -> None:
        """Test requests exceeding limit are rejected."""
        limiter = RateLimiter(max_per_subject=3, window_seconds=60)

        assert limiter.allow("test.subject") is True
        assert limiter.allow("test.subject") is True
        assert limiter.allow("test.subject") is True
        assert limiter.allow("test.subject") is False
        assert limiter.allow("test.subject") is False

    def test_allow_different_subjects(self) -> None:
        """Test different subjects have separate limits."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        assert limiter.allow("subject.a") is True
        assert limiter.allow("subject.a") is True
        assert limiter.allow("subject.a") is False  # Limit reached

        assert limiter.allow("subject.b") is True  # Different subject
        assert limiter.allow("subject.b") is True
        assert limiter.allow("subject.b") is False  # Limit reached

    def test_allow_null_subject(self) -> None:
        """Test None subject uses 'unknown' key."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        assert limiter.allow(None) is True
        assert limiter.allow(None) is True
        assert limiter.allow(None) is False

    def test_allow_window_expiry(self) -> None:
        """Test window expiry resets limit."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=1)

        # Use up the limit
        assert limiter.allow("test") is True
        assert limiter.allow("test") is True
        assert limiter.allow("test") is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        assert limiter.allow("test") is True

    def test_check_without_increment(self) -> None:
        """Test check method doesn't increment counter."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        # Check doesn't increment
        assert limiter.check("test") is True
        assert limiter.check("test") is True
        assert limiter.check("test") is True

        # Allow does increment
        assert limiter.allow("test") is True
        assert limiter.allow("test") is True
        assert limiter.allow("test") is False

        # Check reflects current state
        assert limiter.check("test") is False

    def test_check_null_subject(self) -> None:
        """Test check with None subject."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)
        assert limiter.check(None) is True

    def test_check_nonexistent_subject(self) -> None:
        """Test check for subject that doesn't exist yet."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)
        assert limiter.check("never.seen") is True

    def test_get_remaining_full_limit(self) -> None:
        """Test get_remaining with full limit available."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        assert limiter.get_remaining("test") == 5

    def test_get_remaining_partial(self) -> None:
        """Test get_remaining after some requests."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)

        limiter.allow("test")
        limiter.allow("test")
        limiter.allow("test")

        assert limiter.get_remaining("test") == 2

    def test_get_remaining_exhausted(self) -> None:
        """Test get_remaining when limit exhausted."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        limiter.allow("test")
        limiter.allow("test")

        assert limiter.get_remaining("test") == 0

    def test_get_remaining_null_subject(self) -> None:
        """Test get_remaining with None subject."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        assert limiter.get_remaining(None) == 5

    def test_reset_single_subject(self) -> None:
        """Test reset for single subject."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        limiter.allow("test.a")
        limiter.allow("test.a")
        limiter.allow("test.b")
        limiter.allow("test.b")

        # Both exhausted
        assert limiter.allow("test.a") is False
        assert limiter.allow("test.b") is False

        # Reset only test.a
        limiter.reset("test.a")

        # test.a should be allowed, test.b still exhausted
        assert limiter.allow("test.a") is True
        assert limiter.allow("test.b") is False

    def test_reset_all_subjects(self) -> None:
        """Test reset for all subjects."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        limiter.allow("test.a")
        limiter.allow("test.a")
        limiter.allow("test.b")
        limiter.allow("test.b")

        # Both exhausted
        assert limiter.allow("test.a") is False
        assert limiter.allow("test.b") is False

        # Reset all
        limiter.reset()

        # Both should be allowed
        assert limiter.allow("test.a") is True
        assert limiter.allow("test.b") is True

    def test_reset_nonexistent_subject(self) -> None:
        """Test reset for subject that doesn't exist (no error)."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        limiter.reset("nonexistent")  # Should not raise

    def test_get_stats_empty(self) -> None:
        """Test get_stats with no entries."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        stats = limiter.get_stats()
        assert stats == {}

    def test_get_stats_with_entries(self) -> None:
        """Test get_stats with entries."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)

        limiter.allow("test.a")
        limiter.allow("test.a")
        limiter.allow("test.b")

        stats = limiter.get_stats()

        assert "test.a" in stats
        assert stats["test.a"]["count"] == 2
        assert stats["test.a"]["remaining"] == 3

        assert "test.b" in stats
        assert stats["test.b"]["count"] == 1
        assert stats["test.b"]["remaining"] == 4

    def test_get_stats_window_remaining(self) -> None:
        """Test get_stats includes window_remaining_seconds."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=60)
        limiter.allow("test")

        stats = limiter.get_stats()

        assert "window_remaining_seconds" in stats["test"]
        assert 0 <= stats["test"]["window_remaining_seconds"] <= 60

    def test_thread_safety(self) -> None:
        """Test rate limiter is thread-safe."""
        limiter = RateLimiter(max_per_subject=100, window_seconds=60)
        results = []

        def make_request() -> bool:
            return limiter.allow("concurrent.test")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(200)]
            results = [f.result() for f in futures]

        # Exactly 100 should be allowed
        allowed = sum(1 for r in results if r)
        denied = sum(1 for r in results if not r)

        assert allowed == 100
        assert denied == 100

    def test_window_boundary_with_real_time(self) -> None:
        """Test behavior at window boundary with real time.

        This test verifies that the window resets properly.
        Uses a short window and real sleep to avoid complex mocking.
        """
        limiter = RateLimiter(max_per_subject=2, window_seconds=1)

        # Fill the limit
        assert limiter.allow("test") is True
        assert limiter.allow("test") is True
        assert limiter.allow("test") is False

        # Wait for window to expire (slightly more than 1 second)
        time.sleep(1.05)

        # Should be allowed again after window expires
        assert limiter.allow("test") is True
        assert limiter.allow("test") is True
        assert limiter.allow("test") is False

    def test_max_per_subject_one(self) -> None:
        """Test with max_per_subject of 1."""
        limiter = RateLimiter(max_per_subject=1, window_seconds=60)

        assert limiter.allow("test") is True
        assert limiter.allow("test") is False
        assert limiter.allow("test") is False

    def test_large_window(self) -> None:
        """Test with large window size."""
        limiter = RateLimiter(max_per_subject=5, window_seconds=3600)

        for _ in range(5):
            assert limiter.allow("test") is True

        assert limiter.allow("test") is False
        assert limiter.get_remaining("test") == 0

    def test_many_subjects(self) -> None:
        """Test with many different subjects."""
        limiter = RateLimiter(max_per_subject=2, window_seconds=60)

        for i in range(100):
            subject = f"subject.{i}"
            assert limiter.allow(subject) is True
            assert limiter.allow(subject) is True
            assert limiter.allow(subject) is False

        stats = limiter.get_stats()
        assert len(stats) == 100
