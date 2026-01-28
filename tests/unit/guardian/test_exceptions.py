"""Unit tests for Guardian service exceptions."""

import pytest

from guardian.logic.exceptions import (
    AdvisoryParseError,
    AlerterError,
    GuardianError,
    NatsConnectionError,
    PagerDutyAlertError,
    RateLimitExceededError,
    SlackAlertError,
    WebhookAlertError,
)


class TestGuardianError:
    """Tests for GuardianError base class."""

    def test_init_with_message(self) -> None:
        """Test initialization with message."""
        error = GuardianError("test error")
        assert error.message == "test error"
        assert error.retryable is False
        assert str(error) == "test error"

    def test_init_with_retryable(self) -> None:
        """Test initialization with retryable flag."""
        error = GuardianError("test error", retryable=True)
        assert error.message == "test error"
        assert error.retryable is True

    def test_is_exception(self) -> None:
        """Test GuardianError is an Exception."""
        error = GuardianError("test")
        assert isinstance(error, Exception)


class TestAdvisoryParseError:
    """Tests for AdvisoryParseError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = AdvisoryParseError("invalid JSON")
        assert error.message == "invalid JSON"
        assert error.retryable is False

    def test_is_guardian_error(self) -> None:
        """Test AdvisoryParseError inherits from GuardianError."""
        error = AdvisoryParseError("test")
        assert isinstance(error, GuardianError)

    def test_not_retryable(self) -> None:
        """Test parse errors are never retryable."""
        error = AdvisoryParseError("malformed data")
        assert error.retryable is False


class TestAlerterError:
    """Tests for AlerterError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = AlerterError("TestAlerter", "connection failed")
        assert error.alerter_name == "TestAlerter"
        assert error.message == "TestAlerter: connection failed"
        assert error.retryable is True  # Default

    def test_init_not_retryable(self) -> None:
        """Test initialization with retryable=False."""
        error = AlerterError("TestAlerter", "invalid config", retryable=False)
        assert error.retryable is False

    def test_is_guardian_error(self) -> None:
        """Test AlerterError inherits from GuardianError."""
        error = AlerterError("Test", "msg")
        assert isinstance(error, GuardianError)


class TestSlackAlertError:
    """Tests for SlackAlertError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = SlackAlertError("webhook failed")
        assert error.alerter_name == "SlackAlerter"
        assert "webhook failed" in error.message
        assert error.retryable is True  # Default

    def test_init_not_retryable(self) -> None:
        """Test initialization with retryable=False."""
        error = SlackAlertError("invalid webhook URL", retryable=False)
        assert error.retryable is False

    def test_is_alerter_error(self) -> None:
        """Test SlackAlertError inherits from AlerterError."""
        error = SlackAlertError("test")
        assert isinstance(error, AlerterError)
        assert isinstance(error, GuardianError)


class TestPagerDutyAlertError:
    """Tests for PagerDutyAlertError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = PagerDutyAlertError("API returned 500")
        assert error.alerter_name == "PagerDutyAlerter"
        assert "API returned 500" in error.message
        assert error.retryable is True  # Default

    def test_init_not_retryable(self) -> None:
        """Test initialization with retryable=False."""
        error = PagerDutyAlertError("invalid routing key", retryable=False)
        assert error.retryable is False

    def test_is_alerter_error(self) -> None:
        """Test PagerDutyAlertError inherits from AlerterError."""
        error = PagerDutyAlertError("test")
        assert isinstance(error, AlerterError)
        assert isinstance(error, GuardianError)


class TestWebhookAlertError:
    """Tests for WebhookAlertError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = WebhookAlertError("connection timeout")
        assert error.alerter_name == "WebhookAlerter"
        assert "connection timeout" in error.message
        assert error.retryable is True  # Default

    def test_init_not_retryable(self) -> None:
        """Test initialization with retryable=False."""
        error = WebhookAlertError("invalid URL", retryable=False)
        assert error.retryable is False

    def test_is_alerter_error(self) -> None:
        """Test WebhookAlertError inherits from AlerterError."""
        error = WebhookAlertError("test")
        assert isinstance(error, AlerterError)
        assert isinstance(error, GuardianError)


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = RateLimitExceededError("document.process", 5, 60)
        assert error.subject == "document.process"
        assert error.limit == 5
        assert error.window_seconds == 60
        assert "document.process" in error.message
        assert "5" in error.message
        assert "60" in error.message

    def test_not_retryable(self) -> None:
        """Test rate limit errors are never retryable."""
        error = RateLimitExceededError("test", 10, 30)
        assert error.retryable is False

    def test_is_guardian_error(self) -> None:
        """Test RateLimitExceededError inherits from GuardianError."""
        error = RateLimitExceededError("test", 5, 60)
        assert isinstance(error, GuardianError)


class TestNatsConnectionError:
    """Tests for NatsConnectionError."""

    def test_init(self) -> None:
        """Test initialization."""
        error = NatsConnectionError("connection refused")
        assert error.message == "connection refused"
        assert error.retryable is True

    def test_is_guardian_error(self) -> None:
        """Test NatsConnectionError inherits from GuardianError."""
        error = NatsConnectionError("test")
        assert isinstance(error, GuardianError)

    def test_always_retryable(self) -> None:
        """Test NATS connection errors are always retryable."""
        error = NatsConnectionError("failed to connect")
        assert error.retryable is True
