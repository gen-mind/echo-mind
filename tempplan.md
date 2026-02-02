# EchoMind Implementation Plan: Teams, File Upload & RBAC

> **Status**: In Progress
> **Created**: 2026-02-02
> **Last Updated**: 2026-02-02

---

## Overview

This plan covers 6 major implementation areas:

1. **Teams Schema** - Database models, proto definitions, migrations
2. **RBAC Documentation** - Detailed permission matrix and enforcement
3. **Streaming Downloads** - Refactor connectors for memory-efficient downloads
4. **Upload API** - Pre-signed URL flow for direct uploads
5. **Upload UI** - Documents page with tabs and drag-drop upload
6. **Ingestor Update** - Handle user/team/org collection routing

---

## Phase 1: Teams Schema (Proto + SQLAlchemy + Migration)

### 1.1 Proto Definitions

**File**: `src/proto/public/team.proto` (NEW)

```protobuf
syntax = "proto3";
package echomind.public;

import "google/protobuf/timestamp.proto";
import "common.proto";

// Team within an organization
message Team {
  int32 id = 1;
  string name = 2;
  string description = 3;
  int32 leader_id = 4;           // User ID of team lead
  int32 created_by = 5;          // User who created the team
  int32 member_count = 6;        // Computed field
  google.protobuf.Timestamp creation_date = 7;
  google.protobuf.Timestamp last_update = 8;
}

// Team membership with role
message TeamMember {
  int32 team_id = 1;
  int32 user_id = 2;
  string role = 3;               // "member" or "lead"
  google.protobuf.Timestamp added_at = 4;
  int32 added_by = 5;
}

// Team member with user details (for listing)
message TeamMemberWithUser {
  int32 user_id = 1;
  string user_name = 2;
  string email = 3;
  string first_name = 4;
  string last_name = 5;
  string role = 6;
  google.protobuf.Timestamp added_at = 7;
}

// ===== API Request/Response Messages =====

message CreateTeamRequest {
  string name = 1;
  optional string description = 2;
  optional int32 leader_id = 3;  // Defaults to creator
}

message UpdateTeamRequest {
  int32 id = 1;
  optional string name = 2;
  optional string description = 3;
  optional int32 leader_id = 4;
}

message ListTeamsRequest {
  echomind.common.PaginationRequest pagination = 1;
  optional bool include_member_count = 2;
}

message ListTeamsResponse {
  repeated Team teams = 1;
  echomind.common.PaginationResponse pagination = 2;
}

message GetTeamResponse {
  Team team = 1;
  repeated TeamMemberWithUser members = 2;
}

message AddTeamMemberRequest {
  int32 team_id = 1;
  int32 user_id = 2;
  string role = 3;  // "member" or "lead"
}

message RemoveTeamMemberRequest {
  int32 team_id = 1;
  int32 user_id = 2;
}

message UpdateTeamMemberRoleRequest {
  int32 team_id = 1;
  int32 user_id = 2;
  string role = 3;
}

message ListUserTeamsRequest {
  echomind.common.PaginationRequest pagination = 1;
}

message ListUserTeamsResponse {
  repeated Team teams = 1;
  echomind.common.PaginationResponse pagination = 2;
}
```

**Update**: `src/proto/public/connector.proto`
- Change `CONNECTOR_SCOPE_GROUP` to `CONNECTOR_SCOPE_TEAM` (breaking change requires migration plan)

**Update**: `scripts/generate_proto.sh`
- Add `team.proto` to TypeScript index.ts exports

### 1.2 SQLAlchemy Models

**File**: `src/echomind_lib/db/models/team.py` (NEW)

```python
"""Team ORM model."""

from typing import TYPE_CHECKING

from echomind_lib.db.models.base import (
    TIMESTAMP,
    Base,
    ForeignKey,
    Integer,
    Mapped,
    SmallInteger,
    String,
    Text,
    datetime,
    mapped_column,
    relationship,
)

if TYPE_CHECKING:
    from echomind_lib.db.models.user import User


class Team(Base):
    """Teams for grouping users and resources."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    leader_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    # Relationships
    leader: Mapped["User | None"] = relationship(foreign_keys=[leader_id])
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    """Team membership with role."""

    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    adder: Mapped["User"] = relationship(foreign_keys=[added_by])
```

**Update**: `src/echomind_lib/db/models/connector.py`
- Add `team_id: Mapped[int | None]` foreign key

**Update**: `src/echomind_lib/db/models/__init__.py`
- Export `Team`, `TeamMember`

### 1.3 CRUD Operations

**File**: `src/echomind_lib/db/crud/team.py` (NEW)

Operations needed:
- `create_team(session, obj_in, created_by)` - Create team
- `get_by_id_active(session, team_id)` - Get non-deleted team
- `get_multi_active(session, offset, limit)` - List teams
- `get_by_user(session, user_id)` - Get teams user belongs to
- `add_member(session, team_id, user_id, role, added_by)` - Add member
- `remove_member(session, team_id, user_id)` - Remove member
- `update_member_role(session, team_id, user_id, role)` - Change role
- `get_members(session, team_id)` - List team members with user details
- `is_member(session, team_id, user_id)` - Check membership
- `is_lead(session, team_id, user_id)` - Check if user is lead
- `soft_delete(session, team_id, user_id)` - Soft delete team
- `count_members(session, team_id)` - Count team members

**Update**: `src/echomind_lib/db/crud/__init__.py`
- Export `TeamCRUD`, `team_crud`

### 1.4 Database Migration

**File**: `src/migration/migrations/versions/20260202_120000_add_teams.py` (NEW)

```python
"""Add teams and team_members tables.

Revision ID: 002_add_teams
Revises: 001_initial
Create Date: 2026-02-02 12:00:00.000000
"""

def upgrade() -> None:
    # Create teams table
    op.create_table(
        "teams",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["leader_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_teams_deleted_date", "teams", ["deleted_date"])
    op.create_index("ix_teams_leader_id", "teams", ["leader_id"])

    # Create team_members table
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="'member'"),
        sa.Column("added_at", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("added_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("team_id", "user_id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"]),
    )
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])

    # Add team_id to connectors (nullable, for backward compatibility)
    op.add_column("connectors", sa.Column("team_id", sa.SmallInteger(), nullable=True))
    op.create_foreign_key("fk_connectors_team_id", "connectors", "teams", ["team_id"], ["id"])
    op.create_index("ix_connectors_team_id", "connectors", ["team_id"])

def downgrade() -> None:
    op.drop_index("ix_connectors_team_id", table_name="connectors")
    op.drop_constraint("fk_connectors_team_id", "connectors", type_="foreignkey")
    op.drop_column("connectors", "team_id")
    op.drop_table("team_members")
    op.drop_table("teams")
```

### 1.5 API Routes

**File**: `src/api/routes/teams.py` (NEW)

Endpoints:
- `POST /api/v1/teams` - Create team (admin+)
- `GET /api/v1/teams` - List teams (filtered by access)
- `GET /api/v1/teams/{id}` - Get team with members
- `PUT /api/v1/teams/{id}` - Update team (admin+)
- `DELETE /api/v1/teams/{id}` - Delete team (admin+)
- `POST /api/v1/teams/{id}/members` - Add member (admin+)
- `DELETE /api/v1/teams/{id}/members/{user_id}` - Remove member (admin+)
- `PUT /api/v1/teams/{id}/members/{user_id}` - Update member role (admin+)
- `GET /api/v1/users/me/teams` - Get current user's teams

**File**: `src/api/logic/team_service.py` (NEW)

Business logic with RBAC checks.

### 1.6 Tests

**Directory**: `tests/unit/api/routes/test_teams.py` (NEW)
**Directory**: `tests/unit/api/logic/test_team_service.py` (NEW)
**Directory**: `tests/unit/echomind_lib/db/crud/test_team.py` (NEW)

Test coverage requirements:
- CRUD operations (create, read, update, delete)
- Membership operations (add, remove, update role)
- Permission checks (admin can create, allowed cannot)
- Edge cases (duplicate names, removing last lead, etc.)

---

## Phase 2: RBAC Documentation & Enforcement

### 2.1 Update Documentation

**File**: `docs/rbac.md` (NEW)

Detailed permission matrix for:
- Teams (create, view, edit, delete, manage members)
- Connectors (create personal/team/org, view, edit, delete)
- Documents (view, upload, delete)
- Chat (full access for all)
- Users (admin only)
- LLMs/Embeddings (superadmin only)

### 2.2 Permission Enforcement Points

| Layer | File | Changes |
|-------|------|---------|
| API Routes | `src/api/routes/*.py` | Add RBAC decorators |
| Service Logic | `src/api/logic/*_service.py` | Add ownership checks |
| CRUD | `src/echomind_lib/db/crud/*.py` | Add scope filtering |
| Frontend | `src/web/src/auth/usePermissions.ts` | Add team permissions |

### 2.3 Permission Helper

**File**: `src/api/logic/permissions.py` (NEW)

```python
class PermissionChecker:
    """RBAC permission checking utilities."""

    async def can_view_connector(self, user: TokenUser, connector: Connector) -> bool:
        """Check if user can view a connector."""

    async def can_edit_connector(self, user: TokenUser, connector: Connector) -> bool:
        """Check if user can edit a connector."""

    async def can_create_connector(self, user: TokenUser, scope: str, team_id: int | None) -> bool:
        """Check if user can create a connector with given scope."""

    async def get_accessible_team_ids(self, user: TokenUser) -> list[int]:
        """Get team IDs user has access to."""

    async def get_document_filters(self, user: TokenUser) -> dict:
        """Get document query filters based on user access."""
```

---

## Phase 3: Streaming Downloads (Connector Refactor)

### 3.1 Architecture Change

**Current**: `Provider.download_file() -> DownloadedFile(content: bytes)`
**New**: `Provider.stream_to_storage() -> str (minio_path)`

### 3.2 Files to Modify

| File | Changes |
|------|---------|
| `src/connector/logic/providers/base.py` | Add `stream_to_storage()` abstract method |
| `src/connector/logic/providers/google_drive.py` | Implement streaming download |
| `src/connector/logic/providers/onedrive.py` | Implement streaming download |
| `src/connector/logic/connector_service.py` | Use new streaming method |
| `src/echomind_lib/helpers/minio_helper.py` | Add `stream_upload()` method |

### 3.3 Streaming Pattern

```python
async def stream_to_storage(
    self,
    file: FileMetadata,
    config: dict[str, Any],
    minio_client: MinIOClient,
    bucket: str,
    object_key: str,
) -> StreamResult:
    """
    Stream file from source directly to MinIO.

    Uses httpx streaming to avoid loading file into memory.
    """
    url = self._build_download_url(file)

    async with self._client.stream("GET", url, headers=self._auth_headers()) as response:
        if response.status_code != 200:
            raise DownloadError(...)

        # Stream to MinIO
        result = await minio_client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=response.aiter_bytes(),
            length=-1,  # Unknown length
            content_type=file.mime_type,
        )

        return StreamResult(
            minio_path=f"minio:{bucket}:{object_key}",
            etag=result.etag,
            size=result.size,
        )
```

### 3.4 Remove File Size Limit

- Remove `max_file_size` from config (or make it optional warning threshold)
- Remove `FileTooLargeError` checks before download
- Keep check only for export operations (Google API hard limit)

---

## Phase 4: Upload API (Pre-signed URLs)

### 4.1 New Endpoints

**File**: `src/api/routes/upload.py` (NEW)

```python
# POST /api/v1/documents/upload/initiate
# Request: { filename, content_type, size }
# Response: { document_id, upload_url, expires_in }

# POST /api/v1/documents/upload/complete
# Request: { document_id }
# Response: { document }

# POST /api/v1/documents/upload/abort
# Request: { document_id }
# Response: { success }
```

### 4.2 Upload Service

**File**: `src/api/logic/upload_service.py` (NEW)

```python
class UploadService:
    """Handle document upload via pre-signed URLs."""

    async def initiate_upload(
        self,
        filename: str,
        content_type: str,
        size: int,
        user: TokenUser,
    ) -> InitiateUploadResponse:
        """
        Initiate upload by creating document record and generating pre-signed URL.

        1. Validate file type
        2. Get or create user's FILE connector
        3. Create document record (status: "uploading")
        4. Generate MinIO pre-signed PUT URL
        5. Return upload details
        """

    async def complete_upload(
        self,
        document_id: int,
        user: TokenUser,
    ) -> Document:
        """
        Complete upload after client finishes.

        1. Verify document exists and is "uploading"
        2. Verify file exists in MinIO
        3. Update document status to "pending"
        4. Publish NATS document.process event
        """

    async def abort_upload(
        self,
        document_id: int,
        user: TokenUser,
    ) -> bool:
        """
        Abort upload and cleanup.

        1. Delete MinIO object if exists
        2. Delete document record
        """
```

### 4.3 System FILE Connector

Auto-create per-user FILE connector on first upload:

```python
async def get_or_create_upload_connector(
    self,
    session: AsyncSession,
    user_id: int,
) -> Connector:
    """Get or create the user's system FILE connector for uploads."""
    connector = await connector_crud.get_by_user_and_type(
        session, user_id, "file", system=True
    )
    if not connector:
        connector = await connector_crud.create(session, obj_in={
            "name": "__system_uploads__",
            "type": "file",
            "config": {"system": True},
            "user_id": user_id,
            "scope": "user",
            "status": "active",
        })
    return connector
```

### 4.4 MinIO Pre-signed URL

**Update**: `src/echomind_lib/helpers/minio_helper.py`

```python
async def generate_upload_url(
    self,
    bucket: str,
    object_key: str,
    content_type: str,
    expires: int = 3600,
) -> str:
    """Generate pre-signed PUT URL for direct upload."""
    return await self._client.presigned_put_object(
        bucket_name=bucket,
        object_name=object_key,
        expires=timedelta(seconds=expires),
    )
```

---

## Phase 5: Upload UI (Documents Page Redesign)

### 5.1 Component Structure

```
src/web/src/features/documents/
├── DocumentsPage.tsx           # Main page with tabs
├── components/
│   ├── DocumentTabs.tsx        # Tab navigation (My, Team, Org, Uploads)
│   ├── DocumentList.tsx        # Document table with actions
│   ├── DocumentFilters.tsx     # Status, connector filters
│   ├── FileUploadDialog.tsx    # Upload modal with drag-drop
│   ├── FileUploadProgress.tsx  # Upload progress indicator
│   └── DocumentActions.tsx     # Row actions (view, delete)
└── hooks/
    ├── useDocuments.ts         # Document queries
    ├── useFileUpload.ts        # Upload mutation with progress
    └── useDocumentTabs.ts      # Tab state management
```

### 5.2 File Upload Dialog

Features:
- Drag-and-drop zone
- File type validation (client-side)
- Size display
- Upload progress bar
- Cancel button
- Error handling with retry

### 5.3 API Client Update

**File**: `src/web/src/api/client.ts`

Add upload method:
```typescript
async upload<T>(endpoint: string, file: File, onProgress?: (percent: number) => void): Promise<T> {
  // 1. Call initiate endpoint to get pre-signed URL
  // 2. PUT file directly to MinIO with progress tracking
  // 3. Call complete endpoint
}
```

### 5.4 Document Tabs

| Tab | Contents | Filter |
|-----|----------|--------|
| My Documents | User's personal docs | `scope=user` |
| Team | Team docs (if in team) | `scope=team, team_id=X` |
| Organization | Org-wide docs | `scope=org` |
| Uploads | Manually uploaded | `connector.type=file` |

---

## Phase 6: Ingestor Collection Routing

### 6.1 Collection Naming Strategy

| Scope | Collection Name | Created By |
|-------|-----------------|------------|
| User | `user_{user_id}` | Ingestor on first doc |
| Team | `team_{team_id}` | Ingestor on first doc |
| Org | `org_{org_id}` | Ingestor on first doc |

### 6.2 Ingestor Changes

**File**: `src/ingestor/logic/ingestor_service.py`

Update `_build_collection_name()`:
```python
def _build_collection_name(
    self,
    scope: str,
    scope_id: str | None,
    user_id: str,
    team_id: int | None,
) -> str:
    """Build Qdrant collection name based on scope."""
    if scope == "user":
        return f"user_{user_id}"
    elif scope == "team":
        if team_id:
            return f"team_{team_id}"
        raise ValueError("team_id required for team scope")
    elif scope == "org":
        if scope_id:
            return f"org_{scope_id}"
        return f"org_default"
    else:
        return f"user_{user_id}"  # Fallback
```

### 6.3 Search Service Changes

**File**: `src/search/` (when implemented)

Search across multiple collections based on user access:
```python
async def search(query: str, user: TokenUser) -> list[SearchResult]:
    collections = []

    # Always include user's personal collection
    collections.append(f"user_{user.id}")

    # Add team collections user belongs to
    user_teams = await team_crud.get_by_user(session, user.id)
    for team in user_teams:
        collections.append(f"team_{team.id}")

    # Add org collection (everyone can see)
    collections.append("org_default")

    # Search all collections
    return await qdrant.multi_collection_search(collections, query)
```

---

## Implementation Order

### Sprint 1: Foundation (Phase 1)
1. ✅ Create `src/proto/public/team.proto`
2. ✅ Run `./scripts/generate_proto.sh`
3. ✅ Create `src/echomind_lib/db/models/team.py`
4. ✅ Update `src/echomind_lib/db/models/__init__.py`
5. ✅ Create `src/echomind_lib/db/crud/team.py`
6. ✅ Update `src/echomind_lib/db/crud/__init__.py`
7. ✅ Create migration `20260202_120000_add_teams.py`
8. ✅ Update `src/migration/migrations/env.py` to import Team models
9. ✅ Create `src/api/routes/teams.py`
10. ✅ Create `src/api/logic/team_service.py`
11. ✅ Update `src/api/main.py` to register teams router
12. ✅ Create unit tests for teams

### Sprint 2: RBAC (Phase 2)
1. Create `docs/rbac.md`
2. Create `src/api/logic/permissions.py`
3. Update connector routes with RBAC
4. Update document routes with RBAC
5. Update frontend usePermissions.ts
6. Create tests for permission checks

### Sprint 3: Streaming (Phase 3)
1. Update MinIO helper with stream_upload
2. Create StreamResult dataclass
3. Update provider base class
4. Refactor Google Drive provider
5. Refactor OneDrive provider
6. Update connector service
7. Remove file size limits
8. Create integration tests

### Sprint 4: Upload API (Phase 4)
1. Create upload routes
2. Create upload service
3. Add pre-signed URL to MinIO helper
4. Create system connector logic
5. Create unit tests

### Sprint 5: Upload UI (Phase 5)
1. Create FileUploadDialog component
2. Create useFileUpload hook
3. Update API client with upload method
4. Redesign DocumentsPage with tabs
5. Create DocumentTabs component
6. Create component tests

### Sprint 6: Collection Routing (Phase 6)
1. Update ingestor collection naming
2. Update search service (when exists)
3. Create integration tests

---

## Definition of Done

Each phase must meet:

- [ ] All code follows CLAUDE.md guidelines
- [ ] Type hints on all functions
- [ ] Docstrings on all public functions
- [ ] Unit tests with >70% coverage
- [ ] Integration tests for critical paths
- [ ] No hardcoded values (use config/env)
- [ ] Emoji logging where applicable
- [ ] Proto regeneration if schema changed
- [ ] Migration tested on fresh DB
- [ ] API documentation updated
- [ ] Frontend types regenerated

---

## Dependencies

### External Libraries (Already in requirements.txt)
- `sqlalchemy[asyncio]>=2.0.0` - ORM
- `alembic>=1.13.0` - Migrations
- `httpx>=0.25.0` - Streaming HTTP
- `miniopy-async>=1.17` - MinIO async client
- `pydantic>=2.0.0` - Validation

### New Dependencies (If Needed)
- None identified

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking change to connector scope | Keep "group" alias, migrate data |
| Large file streaming memory issues | Use chunked iterator, test with 5GB files |
| Pre-signed URL security | Short expiry (1h), validate user owns doc |
| Team deletion with active connectors | Cascade soft-delete, warn in UI |

---

## Notes

- All scope changes from "group" to "team" require data migration
- TypeScript types only generated for public protos (team.proto is public)
- System FILE connector is hidden from UI but visible in API
- Upload progress requires XHR (fetch doesn't support progress)
