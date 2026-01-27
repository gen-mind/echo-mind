"""Unit tests for permissions module."""

from datetime import datetime, timezone

import pytest

from connector.logic.permissions import (
    DocumentPermission,
    ExternalAccess,
    merge_permissions,
)


class TestExternalAccess:
    """Tests for ExternalAccess dataclass."""

    def test_empty_access(self) -> None:
        """Test creating empty access."""
        access = ExternalAccess.empty()

        assert access.external_user_emails == frozenset()
        assert access.external_user_group_ids == frozenset()
        assert access.is_public is False

    def test_public_access(self) -> None:
        """Test creating public access."""
        access = ExternalAccess.public()

        assert access.is_public is True
        assert access.external_user_emails == frozenset()

    def test_for_users(self) -> None:
        """Test creating access for specific users."""
        emails = {"user1@example.com", "user2@example.com"}

        access = ExternalAccess.for_users(emails)

        assert access.external_user_emails == frozenset(emails)
        assert access.is_public is False

    def test_for_users_and_groups(self) -> None:
        """Test creating access for users and groups."""
        emails = {"user@example.com"}
        groups = {"group-123", "group-456"}

        access = ExternalAccess.for_users_and_groups(emails, groups)

        assert access.external_user_emails == frozenset(emails)
        assert access.external_user_group_ids == frozenset(groups)

    def test_can_access_public(self) -> None:
        """Test public documents are accessible to anyone."""
        access = ExternalAccess.public()

        assert access.can_access("anyone@example.com", set()) is True

    def test_can_access_by_email(self) -> None:
        """Test access by email match."""
        access = ExternalAccess.for_users({"user@example.com"})

        assert access.can_access("user@example.com", set()) is True
        assert access.can_access("other@example.com", set()) is False

    def test_can_access_by_group(self) -> None:
        """Test access by group membership."""
        access = ExternalAccess.for_users_and_groups(set(), {"group-123"})

        assert access.can_access("user@example.com", {"group-123"}) is True
        assert access.can_access("user@example.com", {"group-456"}) is False

    def test_can_access_empty_denies(self) -> None:
        """Test empty access denies everyone."""
        access = ExternalAccess.empty()

        assert access.can_access("user@example.com", set()) is False

    def test_is_immutable(self) -> None:
        """Test ExternalAccess is immutable (frozen dataclass)."""
        access = ExternalAccess.empty()

        with pytest.raises(AttributeError):
            access.is_public = True  # type: ignore[misc]

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        access = ExternalAccess(
            external_user_emails=frozenset(["user@example.com"]),
            external_user_group_ids=frozenset(["group-1"]),
            is_public=False,
        )

        data = access.to_dict()

        assert "user@example.com" in data["external_user_emails"]
        assert "group-1" in data["external_user_group_ids"]
        assert data["is_public"] is False

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "external_user_emails": ["user@example.com"],
            "external_user_group_ids": ["group-1"],
            "is_public": True,
        }

        access = ExternalAccess.from_dict(data)

        assert "user@example.com" in access.external_user_emails
        assert "group-1" in access.external_user_group_ids
        assert access.is_public is True

    def test_from_dict_defaults(self) -> None:
        """Test from_dict with missing fields uses defaults."""
        access = ExternalAccess.from_dict({})

        assert access.external_user_emails == frozenset()
        assert access.external_user_group_ids == frozenset()
        assert access.is_public is False


class TestDocumentPermission:
    """Tests for DocumentPermission dataclass."""

    def test_creates_with_access(self) -> None:
        """Test creating permission with access."""
        access = ExternalAccess.for_users({"user@example.com"})

        perm = DocumentPermission(
            document_id=123,
            external_access=access,
        )

        assert perm.document_id == 123
        assert perm.external_access == access
        assert perm.synced_at is not None

    def test_custom_synced_at(self) -> None:
        """Test custom synced_at timestamp."""
        now = datetime.now(timezone.utc)
        access = ExternalAccess.empty()

        perm = DocumentPermission(
            document_id=1,
            external_access=access,
            synced_at=now,
        )

        assert perm.synced_at == now

    def test_to_db_row(self) -> None:
        """Test conversion to database row format."""
        access = ExternalAccess(
            external_user_emails=frozenset(["user@example.com"]),
            external_user_group_ids=frozenset(["group-1"]),
            is_public=False,
        )
        perm = DocumentPermission(document_id=123, external_access=access)

        row = perm.to_db_row()

        assert row["document_id"] == 123
        assert "user@example.com" in row["user_emails"]
        assert "group-1" in row["group_ids"]
        assert row["is_public"] is False
        assert "synced_at" in row


class TestMergePermissions:
    """Tests for merge_permissions function."""

    def test_merge_empty_returns_empty(self) -> None:
        """Test merging no permissions returns empty."""
        result = merge_permissions()

        assert result == ExternalAccess.empty()

    def test_merge_single_returns_same(self) -> None:
        """Test merging single permission returns equivalent."""
        access = ExternalAccess.for_users({"user@example.com"})

        result = merge_permissions(access)

        assert result.external_user_emails == access.external_user_emails

    def test_merge_unions_emails(self) -> None:
        """Test merging unions email sets."""
        access1 = ExternalAccess.for_users({"user1@example.com"})
        access2 = ExternalAccess.for_users({"user2@example.com"})

        result = merge_permissions(access1, access2)

        assert "user1@example.com" in result.external_user_emails
        assert "user2@example.com" in result.external_user_emails

    def test_merge_unions_groups(self) -> None:
        """Test merging unions group sets."""
        access1 = ExternalAccess.for_users_and_groups(set(), {"group-1"})
        access2 = ExternalAccess.for_users_and_groups(set(), {"group-2"})

        result = merge_permissions(access1, access2)

        assert "group-1" in result.external_user_group_ids
        assert "group-2" in result.external_user_group_ids

    def test_merge_public_is_sticky(self) -> None:
        """Test merging with public makes result public."""
        access1 = ExternalAccess.for_users({"user@example.com"})
        access2 = ExternalAccess.public()

        result = merge_permissions(access1, access2)

        assert result.is_public is True

    def test_merge_multiple_permissions(self) -> None:
        """Test merging many permissions."""
        accesses = [
            ExternalAccess.for_users({"user1@example.com"}),
            ExternalAccess.for_users({"user2@example.com"}),
            ExternalAccess.for_users_and_groups(set(), {"group-1"}),
        ]

        result = merge_permissions(*accesses)

        assert len(result.external_user_emails) == 2
        assert len(result.external_user_group_ids) == 1
