"""
Guardian service domain exceptions.

All exceptions raised by Guardian business logic.
"""


class GuardianError(Exception):
    """Base exception for Guardian service errors."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        """
        Initialize Guardian error.

        Args:
            message: Error message.
            retryable: Whether the operation can be retried.
        """
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class AdvisoryParseError(GuardianError):
    """Failed to parse NATS advisory message."""

    def __init__(self, message: str) -> None:
        """
        Initialize parse error.

        Args:
            message: Error message describing parse failure.
        """
        super().__init__(message, retryable=False)


class AlerterError(GuardianError):
    """Failed to send alert via alerter."""

    def __init__(self, alerter_name: str, message: str, retryable: bool = True) -> None:
        """
        Initialize alerter error.

        Args:
            alerter_name: Name of the alerter that failed.
            message: Error message.
            retryable: Whether the alert can be retried.
        """
        self.alerter_name = alerter_name
        super().__init__(f"{alerter_name}: {message}", retryable=retryable)


class SlackAlertError(AlerterError):
    """Failed to send Slack alert."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        """
        Initialize Slack alert error.

        Args:
            message: Error message.
            retryable: Whether the alert can be retried.
        """
        super().__init__("SlackAlerter", message, retryable)


class PagerDutyAlertError(AlerterError):
    """Failed to send PagerDuty alert."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        """
        Initialize PagerDuty alert error.

        Args:
            message: Error message.
            retryable: Whether the alert can be retried.
        """
        super().__init__("PagerDutyAlerter", message, retryable)


class WebhookAlertError(AlerterError):
    """Failed to send webhook alert."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        """
        Initialize webhook alert error.

        Args:
            message: Error message.
            retryable: Whether the alert can be retried.
        """
        super().__init__("WebhookAlerter", message, retryable)


class RateLimitExceededError(GuardianError):
    """Alert rate limit exceeded for subject."""

    def __init__(self, subject: str, limit: int, window_seconds: int) -> None:
        """
        Initialize rate limit error.

        Args:
            subject: The subject that exceeded rate limit.
            limit: Maximum alerts allowed.
            window_seconds: Time window in seconds.
        """
        self.subject = subject
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(
            f"Rate limit exceeded for {subject}: {limit} alerts per {window_seconds}s",
            retryable=False,
        )


class NatsConnectionError(GuardianError):
    """Failed to connect to NATS."""

    def __init__(self, message: str) -> None:
        """
        Initialize NATS connection error.

        Args:
            message: Error message.
        """
        super().__init__(message, retryable=True)
