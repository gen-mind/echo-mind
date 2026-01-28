"""Unit tests for Guardian Service configuration."""

import os
from unittest.mock import patch

import pytest

from guardian.config import GuardianSettings, get_settings, reset_settings


class TestGuardianSettings:
    """Tests for GuardianSettings."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Reset settings after each test."""
        reset_settings()

    def test_default_values(self) -> None:
        """Test default configuration values."""
        settings = GuardianSettings()

        assert settings.enabled is True
        assert settings.health_port == 8080
        assert settings.nats_stream_name == "ECHOMIND_DLQ"
        assert settings.nats_source_stream == "ECHOMIND"
        assert settings.alerters == "logging"
        assert settings.alert_rate_limit_per_subject == 5
        assert settings.alert_rate_limit_window_seconds == 60
        assert settings.log_level == "INFO"

    def test_nats_defaults(self) -> None:
        """Test NATS default configuration."""
        settings = GuardianSettings()

        assert settings.nats_url == "nats://localhost:4222"
        assert settings.nats_consumer_name == "guardian-advisory"
        assert settings.nats_connect_timeout == 5.0
        assert settings.nats_user is None
        assert settings.nats_password is None

    def test_alerter_config_defaults(self) -> None:
        """Test alerter configuration defaults."""
        settings = GuardianSettings()

        assert settings.slack_webhook_url is None
        assert settings.slack_channel is None
        assert settings.pagerduty_routing_key is None
        assert settings.pagerduty_severity == "error"
        assert settings.webhook_url is None
        assert settings.webhook_secret is None
        assert settings.webhook_timeout == 10.0

    def test_env_prefix(self) -> None:
        """Test environment variable prefix."""
        with patch.dict(os.environ, {"GUARDIAN_ENABLED": "false"}):
            settings = GuardianSettings()
            assert settings.enabled is False

    def test_custom_rate_limit_settings(self) -> None:
        """Test custom rate limit settings from environment."""
        with patch.dict(
            os.environ,
            {
                "GUARDIAN_ALERT_RATE_LIMIT_PER_SUBJECT": "10",
                "GUARDIAN_ALERT_RATE_LIMIT_WINDOW_SECONDS": "120",
            },
        ):
            settings = GuardianSettings()
            assert settings.alert_rate_limit_per_subject == 10
            assert settings.alert_rate_limit_window_seconds == 120

    def test_custom_nats_settings(self) -> None:
        """Test custom NATS settings from environment."""
        with patch.dict(
            os.environ,
            {
                "GUARDIAN_NATS_URL": "nats://prod:4222",
                "GUARDIAN_NATS_USER": "guardian",
                "GUARDIAN_NATS_PASSWORD": "secret",
            },
        ):
            settings = GuardianSettings()
            assert settings.nats_url == "nats://prod:4222"
            assert settings.nats_user == "guardian"
            assert settings.nats_password == "secret"

    def test_validate_log_level_valid(self) -> None:
        """Test log level validation with valid values."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with patch.dict(os.environ, {"GUARDIAN_LOG_LEVEL": level}):
                settings = GuardianSettings()
                assert settings.log_level == level.upper()

    def test_validate_log_level_lowercase(self) -> None:
        """Test log level validation normalizes to uppercase."""
        with patch.dict(os.environ, {"GUARDIAN_LOG_LEVEL": "debug"}):
            settings = GuardianSettings()
            assert settings.log_level == "DEBUG"

    def test_validate_log_level_invalid(self) -> None:
        """Test log level validation rejects invalid values."""
        with patch.dict(os.environ, {"GUARDIAN_LOG_LEVEL": "INVALID"}):
            with pytest.raises(ValueError, match="Invalid log level"):
                GuardianSettings()

    def test_validate_alerters_valid(self) -> None:
        """Test alerters validation with valid values."""
        with patch.dict(os.environ, {"GUARDIAN_ALERTERS": "logging,slack,pagerduty,webhook"}):
            settings = GuardianSettings()
            assert settings.alerters == "logging,slack,pagerduty,webhook"

    def test_validate_alerters_single(self) -> None:
        """Test alerters validation with single value."""
        with patch.dict(os.environ, {"GUARDIAN_ALERTERS": "slack"}):
            settings = GuardianSettings()
            assert settings.alerters == "slack"

    def test_validate_alerters_whitespace(self) -> None:
        """Test alerters validation trims whitespace."""
        with patch.dict(os.environ, {"GUARDIAN_ALERTERS": " logging , slack "}):
            settings = GuardianSettings()
            assert settings.alerters == "logging,slack"

    def test_validate_alerters_invalid(self) -> None:
        """Test alerters validation rejects invalid values."""
        with patch.dict(os.environ, {"GUARDIAN_ALERTERS": "logging,invalid"}):
            with pytest.raises(ValueError, match="Invalid alerter"):
                GuardianSettings()

    def test_validate_pagerduty_severity_valid(self) -> None:
        """Test PagerDuty severity validation with valid values."""
        for severity in ["critical", "error", "warning", "info"]:
            with patch.dict(os.environ, {"GUARDIAN_PAGERDUTY_SEVERITY": severity}):
                settings = GuardianSettings()
                assert settings.pagerduty_severity == severity.lower()

    def test_validate_pagerduty_severity_uppercase(self) -> None:
        """Test PagerDuty severity validation normalizes to lowercase."""
        with patch.dict(os.environ, {"GUARDIAN_PAGERDUTY_SEVERITY": "CRITICAL"}):
            settings = GuardianSettings()
            assert settings.pagerduty_severity == "critical"

    def test_validate_pagerduty_severity_invalid(self) -> None:
        """Test PagerDuty severity validation rejects invalid values."""
        with patch.dict(os.environ, {"GUARDIAN_PAGERDUTY_SEVERITY": "invalid"}):
            with pytest.raises(ValueError, match="Invalid PagerDuty severity"):
                GuardianSettings()

    def test_get_alerter_list_single(self) -> None:
        """Test get_alerter_list with single alerter."""
        settings = GuardianSettings()  # Default is "logging"
        assert settings.get_alerter_list() == ["logging"]

    def test_get_alerter_list_multiple(self) -> None:
        """Test get_alerter_list with multiple alerters."""
        with patch.dict(os.environ, {"GUARDIAN_ALERTERS": "logging,slack,webhook"}):
            settings = GuardianSettings()
            assert settings.get_alerter_list() == ["logging", "slack", "webhook"]

    def test_slack_config(self) -> None:
        """Test Slack configuration from environment."""
        with patch.dict(
            os.environ,
            {
                "GUARDIAN_SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
                "GUARDIAN_SLACK_CHANNEL": "#alerts",
            },
        ):
            settings = GuardianSettings()
            assert settings.slack_webhook_url == "https://hooks.slack.com/test"
            assert settings.slack_channel == "#alerts"

    def test_pagerduty_config(self) -> None:
        """Test PagerDuty configuration from environment."""
        with patch.dict(
            os.environ,
            {
                "GUARDIAN_PAGERDUTY_ROUTING_KEY": "test-routing-key",
                "GUARDIAN_PAGERDUTY_SEVERITY": "critical",
            },
        ):
            settings = GuardianSettings()
            assert settings.pagerduty_routing_key == "test-routing-key"
            assert settings.pagerduty_severity == "critical"

    def test_webhook_config(self) -> None:
        """Test webhook configuration from environment."""
        with patch.dict(
            os.environ,
            {
                "GUARDIAN_WEBHOOK_URL": "https://example.com/webhook",
                "GUARDIAN_WEBHOOK_SECRET": "secret123",
                "GUARDIAN_WEBHOOK_TIMEOUT": "15.0",
            },
        ):
            settings = GuardianSettings()
            assert settings.webhook_url == "https://example.com/webhook"
            assert settings.webhook_secret == "secret123"
            assert settings.webhook_timeout == 15.0


class TestGetSettings:
    """Tests for get_settings function."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Reset settings after each test."""
        reset_settings()

    def test_returns_settings(self) -> None:
        """Test get_settings returns GuardianSettings instance."""
        settings = get_settings()
        assert isinstance(settings, GuardianSettings)

    def test_caches_settings(self) -> None:
        """Test settings are cached after first call."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reset_clears_cache(self) -> None:
        """Test reset_settings clears the cache."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()
        assert settings1 is not settings2
