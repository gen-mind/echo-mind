"""
Base alerter interface.

All alerters must implement this interface.
"""

from abc import ABC, abstractmethod

from guardian.logic.advisory_parser import FailureDetails
from guardian.logic.exceptions import AlerterError


class Alerter(ABC):
    """
    Base class for alerters.

    Alerters send notifications when DLQ messages are detected.
    Each alerter implementation handles a specific notification channel.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the alerter name.

        Returns:
            Alerter name for logging.
        """
        pass

    @abstractmethod
    async def send_alert(self, details: FailureDetails) -> None:
        """
        Send an alert about a failed message.

        Args:
            details: Failure details from advisory.

        Raises:
            AlerterError: If alert delivery fails.
        """
        pass

    async def close(self) -> None:
        """
        Close any resources held by the alerter.

        Override if alerter needs cleanup.
        """
        pass


__all__ = ["Alerter", "AlerterError"]
