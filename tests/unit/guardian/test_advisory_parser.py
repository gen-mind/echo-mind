"""Unit tests for NATS advisory message parser."""

import json
from datetime import datetime, timezone

import pytest

from guardian.logic.advisory_parser import AdvisoryParser, FailureDetails
from guardian.logic.exceptions import AdvisoryParseError


class TestFailureDetails:
    """Tests for FailureDetails dataclass."""

    def test_init(self) -> None:
        """Test FailureDetails initialization."""
        timestamp = datetime.now(timezone.utc)
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="ingestor-consumer",
            stream_seq=123,
            deliveries=5,
            reason=None,
            timestamp=timestamp,
            original_subject="document.process",
        )

        assert details.advisory_type == "max_deliveries"
        assert details.stream == "ECHOMIND"
        assert details.consumer == "ingestor-consumer"
        assert details.stream_seq == 123
        assert details.deliveries == 5
        assert details.reason is None
        assert details.timestamp == timestamp
        assert details.original_subject == "document.process"
        assert details.original_payload is None

    def test_to_dict(self) -> None:
        """Test FailureDetails to_dict method."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        details = FailureDetails(
            advisory_type="terminated",
            stream="ECHOMIND",
            consumer="connector-consumer",
            stream_seq=456,
            deliveries=None,
            reason="Processing timeout",
            timestamp=timestamp,
            original_subject="connector.sync",
        )

        result = details.to_dict()

        assert result["advisory_type"] == "terminated"
        assert result["stream"] == "ECHOMIND"
        assert result["consumer"] == "connector-consumer"
        assert result["stream_seq"] == 456
        assert result["deliveries"] is None
        assert result["reason"] == "Processing timeout"
        assert result["timestamp"] == "2025-01-15T10:30:00+00:00"
        assert result["original_subject"] == "connector.sync"

    def test_with_original_payload(self) -> None:
        """Test FailureDetails with original payload."""
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=1,
            deliveries=3,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject=None,
            original_payload=b"original message data",
        )

        assert details.original_payload == b"original message data"


class TestAdvisoryParser:
    """Tests for AdvisoryParser."""

    def test_parse_max_deliveries_advisory(self) -> None:
        """Test parsing MAX_DELIVERIES advisory."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "ingestor-consumer-document-process",
            "stream_seq": 12345,
            "deliveries": 5,
            "timestamp": "2025-01-15T10:30:00Z",
        }

        details = AdvisoryParser.parse(json.dumps(payload).encode())

        assert details.advisory_type == "max_deliveries"
        assert details.stream == "ECHOMIND"
        assert details.consumer == "ingestor-consumer-document-process"
        assert details.stream_seq == 12345
        assert details.deliveries == 5
        assert details.reason is None

    def test_parse_terminated_advisory(self) -> None:
        """Test parsing MSG_TERMINATED advisory."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.terminated",
            "stream": "ECHOMIND",
            "consumer": "connector-consumer-google-drive",
            "stream_seq": 67890,
            "reason": "Processing timeout exceeded",
            "timestamp": "2025-01-15T11:00:00Z",
        }

        details = AdvisoryParser.parse(json.dumps(payload).encode())

        assert details.advisory_type == "terminated"
        assert details.stream == "ECHOMIND"
        assert details.consumer == "connector-consumer-google-drive"
        assert details.stream_seq == 67890
        assert details.deliveries is None
        assert details.reason == "Processing timeout exceeded"

    def test_parse_unknown_advisory_type(self) -> None:
        """Test parsing advisory with unknown type."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.unknown",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 100,
            "timestamp": "2025-01-15T12:00:00Z",
        }

        details = AdvisoryParser.parse(json.dumps(payload).encode())

        assert details.advisory_type == "unknown"

    def test_parse_missing_type(self) -> None:
        """Test parsing advisory with missing type field."""
        payload = {
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 100,
        }

        details = AdvisoryParser.parse(json.dumps(payload).encode())

        assert details.advisory_type == "unknown"

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON raises AdvisoryParseError."""
        with pytest.raises(AdvisoryParseError, match="Invalid JSON"):
            AdvisoryParser.parse(b"not valid json")

    def test_parse_empty_bytes(self) -> None:
        """Test parsing empty bytes raises AdvisoryParseError."""
        with pytest.raises(AdvisoryParseError, match="Invalid JSON"):
            AdvisoryParser.parse(b"")

    def test_parse_dict_directly(self) -> None:
        """Test parse_dict method."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test-consumer",
            "stream_seq": 1,
        }

        details = AdvisoryParser.parse_dict(payload)

        assert details.advisory_type == "max_deliveries"
        assert details.stream == "ECHOMIND"

    def test_parse_missing_fields_uses_defaults(self) -> None:
        """Test missing optional fields use defaults."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
        }

        details = AdvisoryParser.parse_dict(payload)

        assert details.stream == "unknown"
        assert details.consumer == "unknown"
        assert details.stream_seq == 0

    def test_parse_timestamp_with_z_suffix(self) -> None:
        """Test parsing timestamp with Z suffix."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test",
            "stream_seq": 1,
            "timestamp": "2025-01-15T10:30:00Z",
        }

        details = AdvisoryParser.parse_dict(payload)

        assert details.timestamp.year == 2025
        assert details.timestamp.month == 1
        assert details.timestamp.day == 15
        assert details.timestamp.hour == 10
        assert details.timestamp.minute == 30

    def test_parse_timestamp_with_offset(self) -> None:
        """Test parsing timestamp with timezone offset."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test",
            "stream_seq": 1,
            "timestamp": "2025-01-15T10:30:00+05:00",
        }

        details = AdvisoryParser.parse_dict(payload)

        assert details.timestamp is not None

    def test_parse_missing_timestamp_uses_now(self) -> None:
        """Test missing timestamp uses current time."""
        payload = {
            "type": "io.nats.jetstream.advisory.v1.max_deliver",
            "stream": "ECHOMIND",
            "consumer": "test",
            "stream_seq": 1,
        }

        before = datetime.now()
        details = AdvisoryParser.parse_dict(payload)
        after = datetime.now()

        assert before <= details.timestamp <= after


class TestExtractSubjectFromConsumer:
    """Tests for _extract_subject_from_consumer method."""

    def test_extract_with_consumer_keyword(self) -> None:
        """Test extraction with 'consumer' in name."""
        result = AdvisoryParser._extract_subject_from_consumer(
            "ingestor-consumer-document-process"
        )
        assert result == "document.process"

    def test_extract_google_drive_pattern(self) -> None:
        """Test extraction with Google Drive consumer name."""
        result = AdvisoryParser._extract_subject_from_consumer(
            "connector-consumer-google-drive"
        )
        assert result == "google.drive"

    def test_extract_without_consumer_keyword(self) -> None:
        """Test extraction without 'consumer' keyword."""
        result = AdvisoryParser._extract_subject_from_consumer(
            "ingestor-document-process"
        )
        assert result == "document.process"

    def test_extract_single_part(self) -> None:
        """Test extraction with single part consumer name returns that part."""
        result = AdvisoryParser._extract_subject_from_consumer("test")
        # Single part consumer names still get processed - returns None when empty after extraction
        # Since "test" has no "consumer" and only 1 element, subject_parts is empty
        # Actually the code returns parts[1:] which is [] for single element
        # This means result should be None
        # Let's check the actual behavior:
        # parts = ["test"], no "consumer" found, subject_parts = parts[1:] = []
        # Since not subject_parts, return None - but wait, the actual code has a different check
        # After reviewing: if len(parts) > 1: subject_parts = parts[1:]
        # So for ["test"], len(parts) is 1, which is NOT > 1
        # So subject_parts = parts which is ["test"]
        # Then ".".join(["test"]) = "test"
        # So the implementation returns "test" for single-part names
        assert result == "test"

    def test_extract_unknown_consumer(self) -> None:
        """Test extraction with 'unknown' consumer returns None."""
        result = AdvisoryParser._extract_subject_from_consumer("unknown")
        assert result is None

    def test_extract_empty_string(self) -> None:
        """Test extraction with empty string returns None."""
        result = AdvisoryParser._extract_subject_from_consumer("")
        assert result is None

    def test_extract_none(self) -> None:
        """Test extraction with None returns None."""
        # Type ignore since we're testing edge case
        result = AdvisoryParser._extract_subject_from_consumer(None)  # type: ignore
        assert result is None


class TestGetAdvisorySummary:
    """Tests for get_advisory_summary method."""

    def test_summary_max_deliveries(self) -> None:
        """Test summary for max_deliveries advisory."""
        details = FailureDetails(
            advisory_type="max_deliveries",
            stream="ECHOMIND",
            consumer="ingestor-consumer",
            stream_seq=123,
            deliveries=5,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject="document.process",
        )

        summary = AdvisoryParser.get_advisory_summary(details)

        assert "123" in summary
        assert "ECHOMIND" in summary
        assert "5" in summary
        assert "ingestor-consumer" in summary
        assert "exceeded max deliveries" in summary

    def test_summary_terminated(self) -> None:
        """Test summary for terminated advisory."""
        details = FailureDetails(
            advisory_type="terminated",
            stream="ECHOMIND",
            consumer="connector-consumer",
            stream_seq=456,
            deliveries=None,
            reason="timeout exceeded",
            timestamp=datetime.now(timezone.utc),
            original_subject="connector.sync",
        )

        summary = AdvisoryParser.get_advisory_summary(details)

        assert "456" in summary
        assert "ECHOMIND" in summary
        assert "timeout exceeded" in summary
        assert "terminated" in summary

    def test_summary_terminated_no_reason(self) -> None:
        """Test summary for terminated advisory without reason."""
        details = FailureDetails(
            advisory_type="terminated",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=789,
            deliveries=None,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject=None,
        )

        summary = AdvisoryParser.get_advisory_summary(details)

        assert "No reason given" in summary

    def test_summary_unknown_type(self) -> None:
        """Test summary for unknown advisory type."""
        details = FailureDetails(
            advisory_type="unknown",
            stream="ECHOMIND",
            consumer="test-consumer",
            stream_seq=100,
            deliveries=None,
            reason=None,
            timestamp=datetime.now(timezone.utc),
            original_subject=None,
        )

        summary = AdvisoryParser.get_advisory_summary(details)

        assert "Unknown advisory" in summary
        assert "100" in summary
