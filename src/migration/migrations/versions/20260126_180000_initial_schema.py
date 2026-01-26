"""Initial schema with all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-26 18:00:00.000000

Creates all EchoMind database tables:
- users
- llms
- embedding_models
- assistants
- connectors
- documents
- chat_sessions
- chat_messages
- chat_message_feedbacks
- chat_message_documents
- agent_memories
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables."""

    # ============================================
    # USERS TABLE
    # ============================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("groups", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("last_login", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_name"),
        sa.UniqueConstraint("email"),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_external_id", "users", ["external_id"])

    # ============================================
    # LLMS TABLE
    # ============================================
    op.create_table(
        "llms",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default="0.7"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_llms_provider", "llms", ["provider"])
    op.create_index("ix_llms_deleted_date", "llms", ["deleted_date"])

    # ============================================
    # EMBEDDING_MODELS TABLE
    # ============================================
    op.create_table(
        "embedding_models",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("model_dimension", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_embedding_models_model_id", "embedding_models", ["model_id"])
    op.create_index("ix_embedding_models_deleted_date", "embedding_models", ["deleted_date"])

    # ============================================
    # ASSISTANTS TABLE
    # ============================================
    op.create_table(
        "assistants",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("llm_id", sa.SmallInteger(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("task_prompt", sa.Text(), nullable=False),
        sa.Column("starter_messages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["llm_id"], ["llms.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_assistants_deleted_date", "assistants", ["deleted_date"])
    op.create_index("ix_assistants_is_visible", "assistants", ["is_visible"])

    # ============================================
    # CONNECTORS TABLE
    # ============================================
    op.create_table(
        "connectors",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("refresh_freq_minutes", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="'user'"),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="'pending'"),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("last_sync_at", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("docs_analyzed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_connectors_user_id", "connectors", ["user_id"])
    op.create_index("ix_connectors_type", "connectors", ["type"])
    op.create_index("ix_connectors_status", "connectors", ["status"])
    op.create_index("ix_connectors_deleted_date", "connectors", ["deleted_date"])

    # ============================================
    # DOCUMENTS TABLE
    # ============================================
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("connector_id", sa.SmallInteger(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("chunking_session", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="'pending'"),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["parent_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_documents_connector_id", "documents", ["connector_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_connector_source", "documents", ["connector_id", "source_id"], unique=True)

    # ============================================
    # CHAT_SESSIONS TABLE
    # ============================================
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("assistant_id", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default="'New Chat'"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="'chat'"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("last_message_at", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("deleted_date", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assistant_id"], ["assistants.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_deleted_date", "chat_sessions", ["deleted_date"])

    # ============================================
    # CHAT_MESSAGES TABLE
    # ============================================
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parent_message_id", sa.BigInteger(), nullable=True),
        sa.Column("rephrased_query", sa.Text(), nullable=True),
        sa.Column("retrieval_context", postgresql.JSONB(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_message_id"], ["chat_messages.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_chat_messages_chat_session_id", "chat_messages", ["chat_session_id"])
    op.create_index("ix_chat_messages_role", "chat_messages", ["role"])

    # ============================================
    # CHAT_MESSAGE_FEEDBACKS TABLE
    # ============================================
    op.create_table(
        "chat_message_feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_message_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_positive", sa.Boolean(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
        sa.UniqueConstraint("chat_message_id", "user_id", name="uq_feedback_message_user"),
    )

    # ============================================
    # CHAT_MESSAGE_DOCUMENTS TABLE
    # ============================================
    op.create_table(
        "chat_message_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_message_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=True),
        sa.Column("relevance_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
        sa.UniqueConstraint("chat_message_id", "document_id", "chunk_id", name="uq_message_document_chunk"),
    )
    op.create_index("ix_chat_message_documents_message_id", "chat_message_documents", ["chat_message_id"])
    op.create_index("ix_chat_message_documents_document_id", "chat_message_documents", ["document_id"])

    # ============================================
    # AGENT_MEMORIES TABLE
    # ============================================
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_id", sa.Text(), nullable=True),
        sa.Column("importance_score", sa.Numeric(3, 2), nullable=False, server_default="0.5"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("source_session_id", sa.Integer(), nullable=True),
        sa.Column("creation_date", postgresql.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_update", postgresql.TIMESTAMP(), nullable=True),
        sa.Column("user_id_last_update", sa.Integer(), nullable=True),
        sa.Column("expires_at", postgresql.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_session_id"], ["chat_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id_last_update"], ["users.id"]),
    )
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"])
    op.create_index("ix_agent_memories_expires_at", "agent_memories", ["expires_at"])


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("agent_memories")
    op.drop_table("chat_message_documents")
    op.drop_table("chat_message_feedbacks")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("documents")
    op.drop_table("connectors")
    op.drop_table("assistants")
    op.drop_table("embedding_models")
    op.drop_table("llms")
    op.drop_table("users")
