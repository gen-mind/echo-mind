"""
Alert rate limiter.

Prevents alert storms by limiting alerts per subject within a time window.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimitEntry:
    """
    Rate limit tracking entry for a subject.

    Attributes:
        count: Number of alerts in current window.
        window_start: Unix timestamp when window started.
    """

    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """
    Token bucket rate limiter for alerts.

    Limits the number of alerts per subject within a sliding time window.
    Thread-safe for concurrent access.
    """

    def __init__(self, max_per_subject: int, window_seconds: int) -> None:
        """
        Initialize rate limiter.

        Args:
            max_per_subject: Maximum alerts allowed per subject per window.
            window_seconds: Time window in seconds.
        """
        self._max_per_subject = max_per_subject
        self._window_seconds = window_seconds
        self._entries: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self._lock = threading.Lock()

    @property
    def max_per_subject(self) -> int:
        """Get maximum alerts per subject."""
        return self._max_per_subject

    @property
    def window_seconds(self) -> int:
        """Get window size in seconds."""
        return self._window_seconds

    def allow(self, subject: str | None) -> bool:
        """
        Check if an alert is allowed for the given subject.

        If allowed, increments the counter. Thread-safe.

        Args:
            subject: The subject to check. If None, uses "unknown".

        Returns:
            True if alert is allowed, False if rate limited.
        """
        if subject is None:
            subject = "unknown"

        with self._lock:
            now = time.time()
            entry = self._entries[subject]

            # Check if window has expired
            if now - entry.window_start >= self._window_seconds:
                # Reset window
                entry.count = 1
                entry.window_start = now
                return True

            # Check if within limit
            if entry.count < self._max_per_subject:
                entry.count += 1
                return True

            # Rate limited
            return False

    def check(self, subject: str | None) -> bool:
        """
        Check if an alert would be allowed without incrementing.

        Args:
            subject: The subject to check. If None, uses "unknown".

        Returns:
            True if alert would be allowed, False if rate limited.
        """
        if subject is None:
            subject = "unknown"

        with self._lock:
            now = time.time()
            entry = self._entries.get(subject)

            if entry is None:
                return True

            # Check if window has expired
            if now - entry.window_start >= self._window_seconds:
                return True

            # Check if within limit
            return entry.count < self._max_per_subject

    def get_remaining(self, subject: str | None) -> int:
        """
        Get remaining alerts allowed for subject in current window.

        Args:
            subject: The subject to check. If None, uses "unknown".

        Returns:
            Number of remaining alerts allowed.
        """
        if subject is None:
            subject = "unknown"

        with self._lock:
            now = time.time()
            entry = self._entries.get(subject)

            if entry is None:
                return self._max_per_subject

            # Check if window has expired
            if now - entry.window_start >= self._window_seconds:
                return self._max_per_subject

            return max(0, self._max_per_subject - entry.count)

    def reset(self, subject: str | None = None) -> None:
        """
        Reset rate limit for a subject or all subjects.

        Args:
            subject: Subject to reset. If None, resets all subjects.
        """
        with self._lock:
            if subject is None:
                self._entries.clear()
            elif subject in self._entries:
                del self._entries[subject]

    def get_stats(self) -> dict[str, dict[str, int | float]]:
        """
        Get current rate limit statistics.

        Returns:
            Dictionary mapping subjects to their stats.
        """
        with self._lock:
            now = time.time()
            stats = {}

            for subject, entry in self._entries.items():
                window_remaining = max(
                    0.0,
                    self._window_seconds - (now - entry.window_start)
                )
                stats[subject] = {
                    "count": entry.count,
                    "remaining": max(0, self._max_per_subject - entry.count),
                    "window_remaining_seconds": round(window_remaining, 1),
                }

            return stats
