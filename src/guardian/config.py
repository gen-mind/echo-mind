"""
Configuration for the Guardian Service.

Uses Pydantic Settings to load environment variables.
All settings prefixed with GUARDIAN_ for namespace isolation.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GuardianSettings(BaseSettings):
    """
    Settings for the Guardian service.

    All environment variables are prefixed with GUARDIAN_.
    Example: GUARDIAN_NATS_URL, GUARDIAN_ALERTERS
    """

    # Service Settings
    enabled: bool = Field(
        True,
        description="Enable guardian service",
    )
    health_port: int = Field(
        8080,
        description="Health check HTTP port",
    )

    # NATS
    nats_url: str = Field(
        "nats://localhost:4222",
        description="NATS server URL",
    )
    nats_user: str | None = Field(
        None,
        description="NATS username",
    )
    nats_password: str | None = Field(
        None,
        description="NATS password",
    )
    nats_connect_timeout: float = Field(
        5.0,
        description="NATS connection timeout in seconds",
        gt=0,
    )
    nats_stream_name: str = Field(
        "ECHOMIND_DLQ",
        description="NATS stream for DLQ advisories",
    )
    nats_consumer_name: str = Field(
        "guardian-advisory",
        description="NATS consumer durable name",
    )
    nats_source_stream: str = Field(
        "ECHOMIND",
        description="Source stream to monitor for failures",
    )

    # Alerters (comma-separated list)
    alerters: str = Field(
        "logging",
        description="Comma-separated alerter names: logging,slack,pagerduty,webhook",
    )

    # Rate Limiting
    alert_rate_limit_per_subject: int = Field(
        5,
        description="Max alerts per original subject per window",
        ge=1,
    )
    alert_rate_limit_window_seconds: int = Field(
        60,
        description="Rate limit window in seconds",
        ge=1,
    )

    # Slack Alerter
    slack_webhook_url: str | None = Field(
        None,
        description="Slack incoming webhook URL",
    )
    slack_channel: str | None = Field(
        None,
        description="Slack channel override",
    )

    # PagerDuty Alerter
    pagerduty_routing_key: str | None = Field(
        None,
        description="PagerDuty Events API v2 routing key",
    )
    pagerduty_severity: str = Field(
        "error",
        description="PagerDuty severity: critical, error, warning, info",
    )

    # Webhook Alerter
    webhook_url: str | None = Field(
        None,
        description="Generic webhook URL",
    )
    webhook_secret: str | None = Field(
        None,
        description="Webhook HMAC secret for signing",
    )
    webhook_timeout: float = Field(
        10.0,
        description="Webhook request timeout in seconds",
        gt=0,
    )

    # Logging
    log_level: str = Field(
        "INFO",
        description="Logging level",
    )

    model_config = SettingsConfigDict(
        env_prefix="GUARDIAN_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """
        Validate log level is valid.

        Args:
            v: Log level string.

        Returns:
            Uppercase log level.

        Raises:
            ValueError: If log level is invalid.
        """
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @field_validator("alerters")
    @classmethod
    def validate_alerters(cls, v: str) -> str:
        """
        Validate alerters list.

        Args:
            v: Comma-separated alerter names.

        Returns:
            Validated alerters string.

        Raises:
            ValueError: If alerter name is invalid.
        """
        valid_alerters = {"logging", "slack", "pagerduty", "webhook"}
        alerter_list = [a.strip().lower() for a in v.split(",") if a.strip()]

        for alerter in alerter_list:
            if alerter not in valid_alerters:
                raise ValueError(
                    f"Invalid alerter: {alerter}. Must be one of {valid_alerters}"
                )

        return ",".join(alerter_list)

    @field_validator("pagerduty_severity")
    @classmethod
    def validate_pagerduty_severity(cls, v: str) -> str:
        """
        Validate PagerDuty severity.

        Args:
            v: Severity string.

        Returns:
            Lowercase severity.

        Raises:
            ValueError: If severity is invalid.
        """
        valid_severities = {"critical", "error", "warning", "info"}
        if v.lower() not in valid_severities:
            raise ValueError(
                f"Invalid PagerDuty severity: {v}. Must be one of {valid_severities}"
            )
        return v.lower()

    def get_alerter_list(self) -> list[str]:
        """
        Get list of enabled alerters.

        Returns:
            List of alerter names.
        """
        return [a.strip() for a in self.alerters.split(",") if a.strip()]


_settings: GuardianSettings | None = None


def get_settings() -> GuardianSettings:
    """
    Get guardian settings from environment.

    Returns:
        GuardianSettings instance.
    """
    global _settings
    if _settings is None:
        _settings = GuardianSettings()  # type: ignore[call-arg]
    return _settings


def reset_settings() -> None:
    """
    Reset settings for testing.

    Clears the cached settings instance.
    """
    global _settings
    _settings = None
