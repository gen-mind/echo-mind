"""
Unit tests for TeamCRUD operations.

Tests team management and membership functionality.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from echomind_lib.db.crud.team import TeamCRUD


class TestTeamCRUD:
    """Tests for TeamCRUD class."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def crud(self) -> TeamCRUD:
        """Create TeamCRUD instance."""
        return TeamCRUD()

    @pytest.fixture
    def mock_team(self) -> MagicMock:
        """Create a mock team."""
        team = MagicMock()
        team.id = 1
        team.name = "Test Team"
        team.description = "A test team"
        team.leader_id = 10
        team.created_by = 10
        team.creation_date = datetime.now(timezone.utc)
        team.last_update = None
        team.deleted_date = None
        team.members = []
        return team

    @pytest.fixture
    def mock_team_member(self) -> MagicMock:
        """Create a mock team member."""
        member = MagicMock()
        member.team_id = 1
        member.user_id = 20
        member.role = "member"
        member.added_at = datetime.now(timezone.utc)
        member.added_by = 10
        return member

    # =========================================================================
    # get_by_name tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_by_name_found(
        self, crud, mock_session, mock_team
    ) -> None:
        """Test finding a team by name."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_name(mock_session, "Test Team")

        assert result == mock_team
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(
        self, crud, mock_session
    ) -> None:
        """Test get_by_name returns None when team doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_name(mock_session, "Nonexistent")

        assert result is None

    # =========================================================================
    # get_with_members tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_with_members_found(
        self, crud, mock_session, mock_team, mock_team_member
    ) -> None:
        """Test getting a team with members loaded."""
        mock_team.members = [mock_team_member]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team
        mock_session.execute.return_value = mock_result

        result = await crud.get_with_members(mock_session, 1)

        assert result == mock_team
        assert len(result.members) == 1

    @pytest.mark.asyncio
    async def test_get_with_members_not_found(
        self, crud, mock_session
    ) -> None:
        """Test get_with_members returns None for missing team."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.get_with_members(mock_session, 999)

        assert result is None

    # =========================================================================
    # get_by_user tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_by_user_with_teams(
        self, crud, mock_session, mock_team
    ) -> None:
        """Test getting teams for a user."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_team]
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_user(mock_session, 20)

        assert len(result) == 1
        assert result[0] == mock_team

    @pytest.mark.asyncio
    async def test_get_by_user_with_pagination(
        self, crud, mock_session
    ) -> None:
        """Test get_by_user respects pagination parameters."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await crud.get_by_user(mock_session, 20, offset=10, limit=5)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_no_teams(
        self, crud, mock_session
    ) -> None:
        """Test get_by_user returns empty list for user with no teams."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_user(mock_session, 20)

        assert result == []

    # =========================================================================
    # get_by_leader tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_by_leader(
        self, crud, mock_session, mock_team
    ) -> None:
        """Test getting teams led by a user."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_team]
        mock_session.execute.return_value = mock_result

        result = await crud.get_by_leader(mock_session, 10)

        assert len(result) == 1
        assert result[0].leader_id == 10

    # =========================================================================
    # count_members tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_count_members(
        self, crud, mock_session
    ) -> None:
        """Test counting team members."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await crud.count_members(mock_session, 1)

        assert result == 5

    @pytest.mark.asyncio
    async def test_count_members_empty_team(
        self, crud, mock_session
    ) -> None:
        """Test counting members in empty team."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await crud.count_members(mock_session, 1)

        assert result == 0

    # =========================================================================
    # is_member tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_is_member_true(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test is_member returns True for existing member."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        result = await crud.is_member(mock_session, 1, 20)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_member_false(
        self, crud, mock_session
    ) -> None:
        """Test is_member returns False for non-member."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.is_member(mock_session, 1, 999)

        assert result is False

    # =========================================================================
    # is_lead tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_is_lead_true(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test is_lead returns True for lead member."""
        mock_team_member.role = "lead"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        result = await crud.is_lead(mock_session, 1, 20)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_lead_false_for_regular_member(
        self, crud, mock_session
    ) -> None:
        """Test is_lead returns False for regular member."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.is_lead(mock_session, 1, 20)

        assert result is False

    # =========================================================================
    # get_member tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_member_found(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test getting a specific team membership."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        result = await crud.get_member(mock_session, 1, 20)

        assert result == mock_team_member

    @pytest.mark.asyncio
    async def test_get_member_not_found(
        self, crud, mock_session
    ) -> None:
        """Test get_member returns None for non-member."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.get_member(mock_session, 1, 999)

        assert result is None

    # =========================================================================
    # get_members tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_members(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test getting all members of a team."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_team_member]
        mock_session.execute.return_value = mock_result

        result = await crud.get_members(mock_session, 1)

        assert len(result) == 1

    # =========================================================================
    # add_member tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_add_member_success(
        self, crud, mock_session
    ) -> None:
        """Test adding a new member to a team."""
        # Mock get_member to return None (not already a member)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        async def mock_refresh(obj):
            obj.team_id = 1
            obj.user_id = 30
            obj.role = "member"

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await crud.add_member(
            mock_session,
            team_id=1,
            user_id=30,
            role="member",
            added_by=10,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        assert result.user_id == 30
        assert result.role == "member"

    @pytest.mark.asyncio
    async def test_add_member_already_exists(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test adding existing member raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await crud.add_member(
                mock_session,
                team_id=1,
                user_id=20,
                role="member",
                added_by=10,
            )

        assert "already a member" in str(exc_info.value)

    # =========================================================================
    # remove_member tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_remove_member_success(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test removing a member from a team."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        result = await crud.remove_member(mock_session, 1, 20)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_team_member)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_member_not_found(
        self, crud, mock_session
    ) -> None:
        """Test removing non-existent member returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.remove_member(mock_session, 1, 999)

        assert result is False
        mock_session.delete.assert_not_called()

    # =========================================================================
    # update_member_role tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_update_member_role_success(
        self, crud, mock_session, mock_team_member
    ) -> None:
        """Test updating a member's role."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_team_member
        mock_session.execute.return_value = mock_result

        result = await crud.update_member_role(mock_session, 1, 20, "lead")

        assert result.role == "lead"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_member_role_not_found(
        self, crud, mock_session
    ) -> None:
        """Test updating role for non-existent member returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await crud.update_member_role(mock_session, 1, 999, "lead")

        assert result is None

    # =========================================================================
    # get_user_teams_with_role tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_user_teams_with_role(
        self, crud, mock_session, mock_team
    ) -> None:
        """Test getting teams and roles for a user."""
        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_team, "member")]
        mock_session.execute.return_value = mock_result

        result = await crud.get_user_teams_with_role(mock_session, 20)

        assert len(result) == 1
        assert result[0][0] == mock_team
        assert result[0][1] == "member"

    # =========================================================================
    # get_team_ids_for_user tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_team_ids_for_user(
        self, crud, mock_session
    ) -> None:
        """Test getting list of team IDs for a user."""
        mock_result = MagicMock()
        mock_result.all.return_value = [(1,), (2,), (3,)]
        mock_session.execute.return_value = mock_result

        result = await crud.get_team_ids_for_user(mock_session, 20)

        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_get_team_ids_for_user_no_teams(
        self, crud, mock_session
    ) -> None:
        """Test getting team IDs for user with no teams."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await crud.get_team_ids_for_user(mock_session, 999)

        assert result == []

    # =========================================================================
    # create_with_founder tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_create_with_founder(
        self, crud, mock_session
    ) -> None:
        """Test creating a team with founder as lead member."""
        async def mock_refresh(obj):
            if hasattr(obj, 'name'):
                obj.id = 1

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await crud.create_with_founder(
            mock_session,
            name="New Team",
            description="A new team",
            created_by=10,
        )

        # Should add team and one member
        assert mock_session.add.call_count == 2
        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_create_with_founder_different_leader(
        self, crud, mock_session
    ) -> None:
        """Test creating a team with different leader than creator."""
        async def mock_refresh(obj):
            if hasattr(obj, 'name'):
                obj.id = 1

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        await crud.create_with_founder(
            mock_session,
            name="New Team",
            description="A new team",
            created_by=10,
            leader_id=20,  # Different from creator
        )

        # Should add team and two members (creator + leader)
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_create_with_founder_leader_same_as_creator(
        self, crud, mock_session
    ) -> None:
        """Test creating team where leader is same as creator."""
        async def mock_refresh(obj):
            if hasattr(obj, 'name'):
                obj.id = 1

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        await crud.create_with_founder(
            mock_session,
            name="New Team",
            description="A new team",
            created_by=10,
            leader_id=10,  # Same as creator
        )

        # Should only add team and one member (not duplicate)
        assert mock_session.add.call_count == 2

