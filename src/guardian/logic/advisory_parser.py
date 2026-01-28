"""
NATS JetStream advisory message parser.

Parses advisory JSON payloads for MAX_DELIVERIES and MSG_TERMINATED events.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from guardian.logic.exceptions import AdvisoryParseError

logger = logging.getLogger("echomind-guardian")


@dataclass
class FailureDetails:
    """
    Details about a failed message from NATS advisory.

    Attributes:
        advisory_type: Type of advisory (max_deliveries or terminated).
        stream: Name of the stream.
        consumer: Name of the consumer.
        stream_seq: Sequence number in the stream.
        deliveries: Number of delivery attempts (for max_deliveries).
        reason: Termination reason (for terminated).
        timestamp: When the advisory was generated.
        original_subject: Extracted original subject from consumer name.
        original_payload: Original message payload if available.
    """

    advisory_type: str
    stream: str
    consumer: str
    stream_seq: int
    deliveries: int | None
    reason: str | None
    timestamp: datetime
    original_subject: str | None
    original_payload: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "advisory_type": self.advisory_type,
            "stream": self.stream,
            "consumer": self.consumer,
            "stream_seq": self.stream_seq,
            "deliveries": self.deliveries,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "original_subject": self.original_subject,
        }


class AdvisoryParser:
    """Parser for NATS JetStream advisory messages."""

    # Advisory type constants
    TYPE_MAX_DELIVERIES = "max_deliveries"
    TYPE_TERMINATED = "terminated"

    # NATS advisory type prefixes
    NATS_TYPE_MAX_DELIVER = "io.nats.jetstream.advisory.v1.max_deliver"
    NATS_TYPE_TERMINATED = "io.nats.jetstream.advisory.v1.terminated"

    @classmethod
    def parse(cls, data: bytes) -> FailureDetails:
        """
        Parse NATS advisory message.

        Args:
            data: Raw advisory message bytes (JSON).

        Returns:
            Parsed FailureDetails.

        Raises:
            AdvisoryParseError: If parsing fails.
        """
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            raise AdvisoryParseError(f"Invalid JSON: {e}") from e

        return cls.parse_dict(payload)

    @classmethod
    def parse_dict(cls, payload: dict[str, Any]) -> FailureDetails:
        """
        Parse advisory from dictionary.

        Args:
            payload: Advisory payload as dictionary.

        Returns:
            Parsed FailureDetails.

        Raises:
            AdvisoryParseError: If required fields are missing.
        """
        try:
            # Determine advisory type
            nats_type = payload.get("type", "")
            if cls.NATS_TYPE_MAX_DELIVER in nats_type:
                advisory_type = cls.TYPE_MAX_DELIVERIES
            elif cls.NATS_TYPE_TERMINATED in nats_type:
                advisory_type = cls.TYPE_TERMINATED
            else:
                advisory_type = "unknown"

            # Extract common fields
            stream = payload.get("stream", "unknown")
            consumer = payload.get("consumer", "unknown")
            stream_seq = payload.get("stream_seq", 0)

            # Extract type-specific fields
            deliveries = payload.get("deliveries") if advisory_type == cls.TYPE_MAX_DELIVERIES else None
            reason = payload.get("reason") if advisory_type == cls.TYPE_TERMINATED else None

            # Parse timestamp
            timestamp_str = payload.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()

            # Extract original subject from consumer name
            # Consumer names follow pattern: {service}-consumer-{subject}
            # e.g., "ingestor-consumer-document-process" -> "document.process"
            original_subject = cls._extract_subject_from_consumer(consumer)

            return FailureDetails(
                advisory_type=advisory_type,
                stream=stream,
                consumer=consumer,
                stream_seq=stream_seq,
                deliveries=deliveries,
                reason=reason,
                timestamp=timestamp,
                original_subject=original_subject,
                original_payload=None,
            )

        except Exception as e:
            if isinstance(e, AdvisoryParseError):
                raise
            raise AdvisoryParseError(f"Failed to parse advisory: {e}") from e

    @classmethod
    def _extract_subject_from_consumer(cls, consumer: str) -> str | None:
        """
        Extract original NATS subject from consumer name.

        Consumer names follow patterns like:
        - "ingestor-consumer-document-process" -> "document.process"
        - "connector-consumer-google-drive" -> "connector.sync.google_drive"

        Args:
            consumer: Consumer name.

        Returns:
            Extracted subject or None if cannot be determined.
        """
        if not consumer or consumer == "unknown":
            return None

        # Try to extract subject from consumer name
        # Common patterns:
        # - {service}-consumer-{subject-with-dashes}
        # - {service}-{subject-with-dashes}

        parts = consumer.split("-")

        # Find "consumer" position if it exists
        try:
            consumer_idx = parts.index("consumer")
            subject_parts = parts[consumer_idx + 1:]
        except ValueError:
            # No "consumer" in name, use parts after first element
            subject_parts = parts[1:] if len(parts) > 1 else parts

        if not subject_parts:
            return None

        # Convert dashes to dots for NATS subject format
        # e.g., ["document", "process"] -> "document.process"
        return ".".join(subject_parts)

    @classmethod
    def get_advisory_summary(cls, details: FailureDetails) -> str:
        """
        Get human-readable summary of failure.

        Args:
            details: Parsed failure details.

        Returns:
            Summary string.
        """
        if details.advisory_type == cls.TYPE_MAX_DELIVERIES:
            return (
                f"Message {details.stream_seq} in {details.stream} exceeded "
                f"max deliveries ({details.deliveries}) for consumer {details.consumer}"
            )
        elif details.advisory_type == cls.TYPE_TERMINATED:
            return (
                f"Message {details.stream_seq} in {details.stream} was terminated "
                f"by consumer {details.consumer}: {details.reason or 'No reason given'}"
            )
        else:
            return (
                f"Unknown advisory for message {details.stream_seq} in {details.stream}"
            )
