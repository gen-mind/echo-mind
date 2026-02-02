"""
Team and TeamMember CRUD operations.
"""

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from echomind_lib.db.crud.base import CRUDBase, SoftDeleteMixin
from echomind_lib.db.models import Team, TeamMember, User


class TeamCRUD(SoftDeleteMixin[Team], CRUDBase[Team]):
    """
    CRUD operations for Team model.

    Teams group users and their resources (connectors, documents).
    Supports membership management with roles (member, lead).
    """

    def __init__(self):
        """Initialize TeamCRUD."""
        super().__init__(Team)

    async def get_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> Team | None:
        """
        Get a team by name.

        Args:
            session: Database session.
            name: Team name.

        Returns:
            Team if found, None otherwise.
        """
        result = await session.execute(
            select(Team)
            .where(Team.deleted_date.is_(None))
            .where(Team.name == name)
        )
        return result.scalar_one_or_none()

    async def get_with_members(
        self,
        session: AsyncSession,
        team_id: int,
    ) -> Team | None:
        """
        Get a team with its members loaded.

        Args:
            session: Database session.
            team_id: Team ID.

        Returns:
            Team with members if found, None otherwise.
        """
        result = await session.execute(
            select(Team)
            .where(Team.id == team_id)
            .where(Team.deleted_date.is_(None))
            .options(selectinload(Team.members).selectinload(TeamMember.user))
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Team]:
        """
        Get teams that a user belongs to.

        Args:
            session: Database session.
            user_id: User ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of teams the user is a member of.
        """
        result = await session.execute(
            select(Team)
            .join(TeamMember, Team.id == TeamMember.team_id)
            .where(Team.deleted_date.is_(None))
            .where(TeamMember.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_leader(
        self,
        session: AsyncSession,
        leader_id: int,
    ) -> Sequence[Team]:
        """
        Get teams led by a specific user.

        Args:
            session: Database session.
            leader_id: Leader user ID.

        Returns:
            List of teams led by the user.
        """
        result = await session.execute(
            select(Team)
            .where(Team.deleted_date.is_(None))
            .where(Team.leader_id == leader_id)
        )
        return result.scalars().all()

    async def count_members(
        self,
        session: AsyncSession,
        team_id: int,
    ) -> int:
        """
        Count members in a team.

        Args:
            session: Database session.
            team_id: Team ID.

        Returns:
            Number of members.
        """
        result = await session.execute(
            select(func.count(TeamMember.user_id))
            .where(TeamMember.team_id == team_id)
        )
        return result.scalar_one()

    async def is_member(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
    ) -> bool:
        """
        Check if a user is a member of a team.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID.

        Returns:
            True if user is a member, False otherwise.
        """
        result = await session.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .where(TeamMember.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    async def is_lead(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
    ) -> bool:
        """
        Check if a user is a lead of a team.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID.

        Returns:
            True if user is a lead, False otherwise.
        """
        result = await session.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .where(TeamMember.user_id == user_id)
            .where(TeamMember.role == "lead")
        )
        return result.scalar_one_or_none() is not None

    async def get_member(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
    ) -> TeamMember | None:
        """
        Get a specific team membership.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID.

        Returns:
            TeamMember if found, None otherwise.
        """
        result = await session.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .where(TeamMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_members(
        self,
        session: AsyncSession,
        team_id: int,
    ) -> Sequence[TeamMember]:
        """
        Get all members of a team with user details.

        Args:
            session: Database session.
            team_id: Team ID.

        Returns:
            List of TeamMember records with user relationship loaded.
        """
        result = await session.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .options(selectinload(TeamMember.user))
        )
        return result.scalars().all()

    async def add_member(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
        role: str,
        added_by: int,
    ) -> TeamMember:
        """
        Add a member to a team.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID to add.
            role: Role (member or lead).
            added_by: User ID of who is adding.

        Returns:
            Created TeamMember record.

        Raises:
            ValueError: If user is already a member.
        """
        # Check if already a member
        existing = await self.get_member(session, team_id, user_id)
        if existing:
            raise ValueError(f"User {user_id} is already a member of team {team_id}")

        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            role=role,
            added_at=datetime.now(timezone.utc),
            added_by=added_by,
        )
        session.add(member)
        await session.flush()
        await session.refresh(member)
        return member

    async def remove_member(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
    ) -> bool:
        """
        Remove a member from a team.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID to remove.

        Returns:
            True if removed, False if not found.
        """
        member = await self.get_member(session, team_id, user_id)
        if member:
            await session.delete(member)
            await session.flush()
            return True
        return False

    async def update_member_role(
        self,
        session: AsyncSession,
        team_id: int,
        user_id: int,
        role: str,
    ) -> TeamMember | None:
        """
        Update a member's role.

        Args:
            session: Database session.
            team_id: Team ID.
            user_id: User ID.
            role: New role (member or lead).

        Returns:
            Updated TeamMember or None if not found.
        """
        member = await self.get_member(session, team_id, user_id)
        if member:
            member.role = role
            await session.flush()
            await session.refresh(member)
            return member
        return None

    async def get_user_teams_with_role(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> list[tuple[Team, str]]:
        """
        Get teams and roles for a user.

        Args:
            session: Database session.
            user_id: User ID.

        Returns:
            List of (Team, role) tuples.
        """
        result = await session.execute(
            select(Team, TeamMember.role)
            .join(TeamMember, Team.id == TeamMember.team_id)
            .where(Team.deleted_date.is_(None))
            .where(TeamMember.user_id == user_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_team_ids_for_user(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> list[int]:
        """
        Get list of team IDs a user belongs to.

        Useful for filtering queries by team membership.

        Args:
            session: Database session.
            user_id: User ID.

        Returns:
            List of team IDs.
        """
        result = await session.execute(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.deleted_date.is_(None))
            .where(TeamMember.user_id == user_id)
        )
        return [row[0] for row in result.all()]

    async def create_with_founder(
        self,
        session: AsyncSession,
        *,
        name: str,
        description: str | None,
        created_by: int,
        leader_id: int | None = None,
    ) -> Team:
        """
        Create a team and add the creator as a member with lead role.

        Args:
            session: Database session.
            name: Team name.
            description: Team description.
            created_by: User ID of creator.
            leader_id: User ID of leader (defaults to creator).

        Returns:
            Created Team with creator as lead member.
        """
        # Use creator as leader if not specified
        actual_leader = leader_id or created_by

        # Create the team
        team = Team(
            name=name,
            description=description,
            leader_id=actual_leader,
            created_by=created_by,
            creation_date=datetime.now(timezone.utc),
        )
        session.add(team)
        await session.flush()

        # Add creator as lead member
        member = TeamMember(
            team_id=team.id,
            user_id=created_by,
            role="lead",
            added_at=datetime.now(timezone.utc),
            added_by=created_by,
        )
        session.add(member)

        # If leader is different from creator, add them too
        if leader_id and leader_id != created_by:
            leader_member = TeamMember(
                team_id=team.id,
                user_id=leader_id,
                role="lead",
                added_at=datetime.now(timezone.utc),
                added_by=created_by,
            )
            session.add(leader_member)

        await session.flush()
        await session.refresh(team)
        return team


team_crud = TeamCRUD()
