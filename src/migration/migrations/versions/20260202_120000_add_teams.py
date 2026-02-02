"""Add teams and team_members tables.

Revision ID: 002_add_teams
Revises: 001_initial
Create Date: 2026-02-02 12:00:00.000000

Creates tables for multi-tenancy support:
- teams: Groups of users with shared resources
- team_members: User membership in teams with roles (member/lead)
- Adds team_id foreign key to connectors for team-scoped resources
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_add_teams"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create teams and team_members tables, add team_id to connectors."""

    # ============================================
    # TEAMS TABLE
    # ============================================
    op.create_table(
        "teams",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "creation_date",
            postgresql.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["leader_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_teams_name", "teams", ["name"])
    op.create_index("ix_teams_leader_id", "teams", ["leader_id"])
    op.create_index("ix_teams_deleted_date", "teams", ["deleted_date"])

    # ============================================
    # TEAM_MEMBERS TABLE
    # ============================================
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role", sa.String(20), nullable=False, server_default="'member'"
        ),
        sa.Column(
            "added_at",
            postgresql.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("added_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("team_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"]),
    )
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])
    op.create_index("ix_team_members_role", "team_members", ["role"])

    # ============================================
    # ADD team_id TO CONNECTORS
    # ============================================
    op.add_column(
        "connectors",
        sa.Column("team_id", sa.SmallInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_connectors_team_id",
        "connectors",
        "teams",
        ["team_id"],
        ["id"],
    )
    op.create_index("ix_connectors_team_id", "connectors", ["team_id"])


def downgrade() -> None:
    """Remove teams tables and team_id from connectors."""
    # Remove team_id from connectors
    op.drop_index("ix_connectors_team_id", table_name="connectors")
    op.drop_constraint("fk_connectors_team_id", "connectors", type_="foreignkey")
    op.drop_column("connectors", "team_id")

    # Drop team_members table
    op.drop_index("ix_team_members_role", table_name="team_members")
    op.drop_index("ix_team_members_user_id", table_name="team_members")
    op.drop_table("team_members")

    # Drop teams table
    op.drop_index("ix_teams_deleted_date", table_name="teams")
    op.drop_index("ix_teams_leader_id", table_name="teams")
    op.drop_index("ix_teams_name", table_name="teams")
    op.drop_table("teams")
