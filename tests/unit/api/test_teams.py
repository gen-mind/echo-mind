"""Unit tests for team management endpoints."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from echomind_lib.models.public import TeamMemberRole


@dataclass
class MockTeam:
    """Mock team ORM object for testing."""

    id: int = 1
    name: str = "Test Team"
    description: str = "A test team"
    leader_id: int | None = 10
    created_by: int = 10
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime | None = None
    user_id_last_update: int | None = None
    deleted_date: datetime | None = None
    members: list = field(default_factory=list)


@dataclass
class MockUser:
    """Mock user ORM object for testing."""

    id: int = 20
    user_name: str = "testuser"
    email: str = "test@example.com"
    first_name: str = "Test"
    last_name: str = "User"


@dataclass
class MockTeamMember:
    """Mock team member ORM object for testing."""

    team_id: int = 1
    user_id: int = 20
    role: str = "member"
    added_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    added_by: int = 10
    user: MockUser = field(default_factory=MockUser)


@dataclass
class MockTokenUser:
    """Mock authenticated user."""

    id: int = 1
    email: str = "test@example.com"
    user_name: str = "testuser"
    first_name: str = "Test"
    last_name: str = "User"
    roles: list[str] = field(default_factory=lambda: ["echomind-allowed"])
    groups: list[str] = field(default_factory=lambda: ["default"])
    external_id: str = "ext-123"


@dataclass
class MockAdminUser:
    """Mock admin user."""

    id: int = 10
    email: str = "admin@example.com"
    user_name: str = "admin"
    first_name: str = "Admin"
    last_name: str = "User"
    roles: list[str] = field(default_factory=lambda: ["echomind-allowed", "echomind-admins"])
    groups: list[str] = field(default_factory=lambda: ["admins"])
    external_id: str = "ext-admin"


class MockResult:
    """Mock SQLAlchemy query result."""

    def __init__(self, data: list[Any]):
        self._data = data

    def scalars(self) -> "MockResult":
        return MockResult(self._data)

    def all(self) -> list[Any]:
        return self._data

    def scalar_one_or_none(self) -> Any | None:
        return self._data[0] if self._data else None


class MockDbSession:
    """Mock async database session with query tracking."""

    def __init__(self):
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self._scalars_result: list[Any] = []

    def set_scalars_result(self, result: list[Any]) -> None:
        """Set the result for scalars().all()."""
        self._scalars_result = result

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: Any, attrs: list[str] | None = None) -> None:
        if hasattr(obj, "id") and obj.id is None:
            obj.id = 1
        if hasattr(obj, "creation_date") and obj.creation_date is None:
            obj.creation_date = datetime.now(timezone.utc)

    async def execute(self, query: Any) -> MockResult:
        return MockResult(self._scalars_result)


class TestTeamEndpoints:
    """Tests for team CRUD endpoints."""

    @pytest.fixture
    def mock_user(self) -> MockTokenUser:
        return MockTokenUser()

    @pytest.fixture
    def mock_admin_user(self) -> MockAdminUser:
        return MockAdminUser()

    @pytest.fixture
    def mock_db(self) -> MockDbSession:
        return MockDbSession()

    @pytest.fixture
    def mock_team(self) -> MockTeam:
        return MockTeam()

    @pytest.fixture
    def mock_team_member(self) -> MockTeamMember:
        return MockTeamMember()

    @pytest.fixture
    def client(
        self,
        mock_db: MockDbSession,
        mock_user: MockTokenUser,
    ) -> TestClient:
        """Create test client with mocked dependencies for regular user."""
        from api.dependencies import get_current_user, get_db_session
        from api.middleware.error_handler import setup_error_handlers
        from api.routes.teams import router

        app = FastAPI()
        setup_error_handlers(app)  # Register error handlers
        app.include_router(router, prefix="/teams")

        async def override_db() -> AsyncGenerator[MockDbSession, None]:
            yield mock_db

        async def override_user() -> MockTokenUser:
            return mock_user

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_current_user] = override_user

        return TestClient(app)

    @pytest.fixture
    def admin_client(
        self,
        mock_db: MockDbSession,
        mock_admin_user: MockAdminUser,
    ) -> TestClient:
        """Create test client with mocked dependencies for admin user."""
        from api.dependencies import get_current_user, get_db_session
        from api.middleware.error_handler import setup_error_handlers
        from api.routes.teams import router

        app = FastAPI()
        setup_error_handlers(app)  # Register error handlers
        app.include_router(router, prefix="/teams")

        async def override_db() -> AsyncGenerator[MockDbSession, None]:
            yield mock_db

        async def override_user() -> MockAdminUser:
            return mock_admin_user

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_current_user] = override_user

        return TestClient(app)

    # =========================================================================
    # list_teams tests
    # =========================================================================

    def test_list_teams_success(
        self,
        client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test listing teams for regular user."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_user = AsyncMock(return_value=[mock_team])
            mock_crud.count_members = AsyncMock(return_value=0)

            response = client.get("/teams")

            assert response.status_code == 200
            data = response.json()
            assert "teams" in data
            assert len(data["teams"]) == 1
            assert data["teams"][0]["name"] == "Test Team"

    def test_list_teams_with_pagination(
        self,
        client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test listing teams with pagination parameters."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_user = AsyncMock(return_value=[mock_team])
            mock_crud.count_members = AsyncMock(return_value=5)

            response = client.get("/teams?page=2&limit=10&include_member_count=true")

            assert response.status_code == 200
            mock_crud.get_by_user.assert_called()

    def test_list_teams_admin_sees_all(
        self,
        admin_client: TestClient,
        mock_db: MockDbSession,
        mock_team: MockTeam,
    ) -> None:
        """Test admin can see all teams."""
        mock_db.set_scalars_result([mock_team])

        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.count_members = AsyncMock(return_value=3)

            response = admin_client.get("/teams")

            assert response.status_code == 200
            # Admin path doesn't call get_by_user
            mock_crud.get_by_user.assert_not_called()

    # =========================================================================
    # get_my_teams tests
    # =========================================================================

    def test_get_my_teams_success(
        self,
        client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test getting user's own teams."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_user = AsyncMock(return_value=[mock_team])
            mock_crud.count_members = AsyncMock(return_value=5)

            response = client.get("/teams/me")

            assert response.status_code == 200
            data = response.json()
            assert len(data["teams"]) == 1
            # member_count comes from count_members call
            mock_crud.count_members.assert_called_once()

    # =========================================================================
    # create_team tests
    # =========================================================================

    def test_create_team_success(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test creating a team as admin."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_name = AsyncMock(return_value=None)
            mock_crud.create_with_founder = AsyncMock(return_value=mock_team)
            mock_crud.count_members = AsyncMock(return_value=1)

            response = admin_client.post(
                "/teams",
                json={
                    "name": "New Team",
                    "description": "A new team",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Test Team"

    def test_create_team_forbidden_for_regular_user(
        self,
        client: TestClient,
    ) -> None:
        """Test creating team forbidden for non-admin."""
        response = client.post(
            "/teams",
            json={
                "name": "New Team",
                "description": "A new team",
            },
        )

        assert response.status_code == 403

    def test_create_team_duplicate_name(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test creating team with duplicate name fails."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_name = AsyncMock(return_value=mock_team)

            response = admin_client.post(
                "/teams",
                json={
                    "name": "Test Team",  # Already exists
                    "description": "A new team",
                },
            )

            assert response.status_code == 409

    # =========================================================================
    # get_team tests
    # =========================================================================

    def test_get_team_success(
        self,
        client: TestClient,
        mock_team: MockTeam,
        mock_team_member: MockTeamMember,
    ) -> None:
        """Test getting a team by ID."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.get_members = AsyncMock(return_value=[mock_team_member])

            response = client.get("/teams/1")

            assert response.status_code == 200
            data = response.json()
            assert data["team"]["name"] == "Test Team"
            assert len(data["members"]) == 1
            assert data["members"][0]["user_name"] == "testuser"

    def test_get_team_not_found(
        self,
        client: TestClient,
    ) -> None:
        """Test getting non-existent team returns 404."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=None)

            response = client.get("/teams/999")

            assert response.status_code == 404

    def test_get_team_forbidden_for_non_member(
        self,
        client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test getting team when not a member returns 403."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=False)

            response = client.get("/teams/1")

            assert response.status_code == 403

    # =========================================================================
    # update_team tests
    # =========================================================================

    def test_update_team_success(
        self,
        admin_client: TestClient,
        mock_db: MockDbSession,
        mock_team: MockTeam,
    ) -> None:
        """Test updating a team as admin lead."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.get_by_name = AsyncMock(return_value=None)
            mock_crud.count_members = AsyncMock(return_value=3)

            response = admin_client.put(
                "/teams/1",
                json={
                    "name": "Updated Name",
                    "description": "Updated description",
                },
            )

            assert response.status_code == 200
            assert mock_team.name == "Updated Name"

    def test_update_team_not_lead(
        self,
        client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test updating team without lead role fails."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=False)

            response = client.put(
                "/teams/1",
                json={"name": "Updated Name"},
            )

            assert response.status_code == 403

    # =========================================================================
    # delete_team tests
    # =========================================================================

    def test_delete_team_success(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test soft deleting a team."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)

            response = admin_client.delete("/teams/1")

            assert response.status_code == 204
            assert mock_team.deleted_date is not None

    def test_delete_team_not_found(
        self,
        admin_client: TestClient,
    ) -> None:
        """Test deleting non-existent team returns 404."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=None)

            response = admin_client.delete("/teams/999")

            assert response.status_code == 404

    # =========================================================================
    # add_team_member tests
    # =========================================================================

    def test_add_team_member_success(
        self,
        admin_client: TestClient,
        mock_db: MockDbSession,
        mock_team: MockTeam,
        mock_team_member: MockTeamMember,
    ) -> None:
        """Test adding a member to a team."""
        mock_user_orm = MagicMock()
        mock_user_orm.id = 20
        mock_db.set_scalars_result([mock_user_orm])

        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.get_member = AsyncMock(return_value=None)
            mock_crud.add_member = AsyncMock(return_value=mock_team_member)

            response = admin_client.post(
                "/teams/1/members",
                json={
                    "user_id": 20,
                    "role": 1,  # TeamMemberRole.TEAM_MEMBER_ROLE_MEMBER = 1
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["user_id"] == 20

    def test_add_team_member_already_exists(
        self,
        admin_client: TestClient,
        mock_db: MockDbSession,
        mock_team: MockTeam,
        mock_team_member: MockTeamMember,
    ) -> None:
        """Test adding existing member fails."""
        mock_user_orm = MagicMock()
        mock_user_orm.id = 20
        mock_db.set_scalars_result([mock_user_orm])

        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.get_member = AsyncMock(return_value=mock_team_member)

            response = admin_client.post(
                "/teams/1/members",
                json={
                    "user_id": 20,
                    "role": 1,  # TeamMemberRole.TEAM_MEMBER_ROLE_MEMBER = 1
                },
            )

            assert response.status_code == 409

    # =========================================================================
    # remove_team_member tests
    # =========================================================================

    def test_remove_team_member_success(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test removing a member from a team."""
        mock_team.leader_id = 10  # Not the user being removed

        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.remove_member = AsyncMock(return_value=True)

            response = admin_client.delete("/teams/1/members/20")

            assert response.status_code == 204

    def test_remove_team_member_cannot_remove_leader(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test cannot remove team leader."""
        mock_team.leader_id = 20  # Trying to remove the leader

        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)

            response = admin_client.delete("/teams/1/members/20")

            assert response.status_code == 403

    # =========================================================================
    # update_team_member_role tests
    # =========================================================================

    def test_update_team_member_role_success(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
        mock_team_member: MockTeamMember,
    ) -> None:
        """Test updating a member's role."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.update_member_role = AsyncMock(return_value=mock_team_member)

            response = admin_client.put(
                "/teams/1/members/20/role",
                json={"role": 2},  # TeamMemberRole.TEAM_MEMBER_ROLE_LEAD = 2
            )

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == 20

    def test_update_team_member_role_not_found(
        self,
        admin_client: TestClient,
        mock_team: MockTeam,
    ) -> None:
        """Test updating role for non-existent member fails."""
        with patch("api.logic.team_service.team_crud") as mock_crud:
            mock_crud.get_by_id = AsyncMock(return_value=mock_team)
            mock_crud.is_member = AsyncMock(return_value=True)
            mock_crud.is_lead = AsyncMock(return_value=True)
            mock_crud.update_member_role = AsyncMock(return_value=None)

            response = admin_client.put(
                "/teams/1/members/999/role",
                json={"role": 2},  # TeamMemberRole.TEAM_MEMBER_ROLE_LEAD = 2
            )

            assert response.status_code == 404
