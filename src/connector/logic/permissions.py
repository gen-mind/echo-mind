"""
Permission handling for document access control.

Tracks who has access to each document for search filtering.
Permissions are synced on every document sync.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ExternalAccess:
    """
    Document access permissions.

    Represents who can access a document for search filtering.
    Immutable to ensure consistency.
    """

    # Emails of users with direct access
    external_user_emails: frozenset[str] = field(default_factory=frozenset)

    # Group IDs with access (e.g., "engineering-team")
    external_user_group_ids: frozenset[str] = field(default_factory=frozenset)

    # Whether document is publicly accessible
    is_public: bool = False

    @classmethod
    def public(cls) -> "ExternalAccess":
        """
        Create access for a publicly accessible document.

        Returns:
            ExternalAccess with is_public=True.
        """
        return cls(
            external_user_emails=frozenset(),
            external_user_group_ids=frozenset(),
            is_public=True,
        )

    @classmethod
    def empty(cls) -> "ExternalAccess":
        """
        Create empty access (fallback when permissions unknown).

        Returns:
            ExternalAccess with no permissions.
        """
        return cls(
            external_user_emails=frozenset(),
            external_user_group_ids=frozenset(),
            is_public=False,
        )

    @classmethod
    def for_users(cls, emails: set[str]) -> "ExternalAccess":
        """
        Create access for a set of users.

        Args:
            emails: Set of user email addresses.

        Returns:
            ExternalAccess for the specified users.
        """
        return cls(
            external_user_emails=frozenset(emails),
            external_user_group_ids=frozenset(),
            is_public=False,
        )

    @classmethod
    def for_users_and_groups(
        cls, emails: set[str], groups: set[str]
    ) -> "ExternalAccess":
        """
        Create access for users and groups.

        Args:
            emails: Set of user email addresses.
            groups: Set of group IDs.

        Returns:
            ExternalAccess for the specified users and groups.
        """
        return cls(
            external_user_emails=frozenset(emails),
            external_user_group_ids=frozenset(groups),
            is_public=False,
        )

    def can_access(self, user_email: str, user_groups: set[str]) -> bool:
        """
        Check if a user can access this document.

        Args:
            user_email: Email of the user.
            user_groups: Set of group IDs the user belongs to.

        Returns:
            True if user has access, False otherwise.
        """
        if self.is_public:
            return True
        if user_email in self.external_user_emails:
            return True
        if user_groups & self.external_user_group_ids:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Returns:
            Dictionary representation.
        """
        return {
            "external_user_emails": list(self.external_user_emails),
            "external_user_group_ids": list(self.external_user_group_ids),
            "is_public": self.is_public,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExternalAccess":
        """
        Create from dictionary (database load).

        Args:
            data: Dictionary from database.

        Returns:
            ExternalAccess instance.
        """
        return cls(
            external_user_emails=frozenset(data.get("external_user_emails", [])),
            external_user_group_ids=frozenset(data.get("external_user_group_ids", [])),
            is_public=data.get("is_public", False),
        )


@dataclass
class DocumentPermission:
    """
    Document permission record for database storage.

    Represents the permission state for a single document.
    """

    document_id: int
    external_access: ExternalAccess
    synced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_db_row(self) -> dict[str, Any]:
        """
        Convert to database row format.

        Returns:
            Dictionary for database insertion.
        """
        return {
            "document_id": self.document_id,
            "user_emails": list(self.external_access.external_user_emails),
            "group_ids": list(self.external_access.external_user_group_ids),
            "is_public": self.external_access.is_public,
            "synced_at": self.synced_at,
        }


def merge_permissions(*accesses: ExternalAccess) -> ExternalAccess:
    """
    Merge multiple ExternalAccess instances into one.

    Useful when a document has multiple permission sources.

    Args:
        *accesses: ExternalAccess instances to merge.

    Returns:
        Merged ExternalAccess with union of all permissions.
    """
    if not accesses:
        return ExternalAccess.empty()

    all_emails: set[str] = set()
    all_groups: set[str] = set()
    is_public = False

    for access in accesses:
        all_emails.update(access.external_user_emails)
        all_groups.update(access.external_user_group_ids)
        is_public = is_public or access.is_public

    return ExternalAccess(
        external_user_emails=frozenset(all_emails),
        external_user_group_ids=frozenset(all_groups),
        is_public=is_public,
    )
