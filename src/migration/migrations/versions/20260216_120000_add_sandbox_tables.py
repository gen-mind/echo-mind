"""Add sandbox_sessions and sandbox_events tables.

Revision ID: 20260216_120000
Revises: 20260210_033000
Create Date: 2026-02-16 12:00:00

Adds tables for ephemeral Docker sandbox container lifecycle tracking.
sandbox_sessions tracks container assignments to chat sessions.
sandbox_events provides an audit log of lifecycle events.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260216_120000'
down_revision = '20260210_033000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sandbox_sessions and sandbox_events tables with indexes."""
    # Create sandbox_sessions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id VARCHAR(255) NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            chat_session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL,
            container_id VARCHAR(255),
            container_name VARCHAR(255),
            status VARCHAR(50) NOT NULL DEFAULT 'warm',
            assigned_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ,
            destroyed_at TIMESTAMPTZ,
            agent_config JSONB DEFAULT '{}'::jsonb,
            message_count INTEGER NOT NULL DEFAULT 0,
            tool_calls_count INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sandbox_sessions_session_id UNIQUE (session_id)
        );
    """)

    # Create sandbox_events table
    op.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_events (
            id BIGSERIAL PRIMARY KEY,
            sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Indexes for sandbox_sessions
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sandbox_sessions_user_created
        ON sandbox_sessions (user_id, created_at DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sandbox_sessions_status_active
        ON sandbox_sessions (status)
        WHERE status != 'destroyed';
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sandbox_sessions_container_id
        ON sandbox_sessions (container_id)
        WHERE container_id IS NOT NULL;
    """)

    # Indexes for sandbox_events
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sandbox_events_session_created
        ON sandbox_events (sandbox_session_id, created_at DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sandbox_events_type_created
        ON sandbox_events (event_type, created_at DESC);
    """)


def downgrade() -> None:
    """Drop sandbox tables and indexes."""
    op.execute("DROP TABLE IF EXISTS sandbox_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS sandbox_sessions CASCADE;")
