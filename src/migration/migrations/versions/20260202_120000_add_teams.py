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
    op.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id SMALLSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            leader_id INTEGER REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            creation_date TIMESTAMP NOT NULL DEFAULT now(),
            last_update TIMESTAMP,
            user_id_last_update INTEGER REFERENCES users(id),
            deleted_date TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_teams_name ON teams (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_teams_leader_id ON teams (leader_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_teams_deleted_date ON teams (deleted_date)")

    # ============================================
    # TEAM_MEMBERS TABLE
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            team_id SMALLINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            added_at TIMESTAMP NOT NULL DEFAULT now(),
            added_by INTEGER NOT NULL REFERENCES users(id),
            PRIMARY KEY (team_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_members_user_id ON team_members (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_members_role ON team_members (role)")

    # ============================================
    # ADD team_id TO CONNECTORS
    # ============================================
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'connectors' AND column_name = 'team_id'
            ) THEN
                ALTER TABLE connectors ADD COLUMN team_id SMALLINT;
                ALTER TABLE connectors ADD CONSTRAINT fk_connectors_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id);
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_connectors_team_id ON connectors (team_id)")


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
