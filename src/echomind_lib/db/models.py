"""
SQLAlchemy ORM models for all EchoMind database tables.

These models map directly to the schema defined in src/db-schema/schema.sql.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from echomind_lib.db.connection import Base


class User(Base):
    """User accounts synced from Authentik OIDC."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    groups: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    last_login: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    connectors: Mapped[list["Connector"]] = relationship(back_populates="user", foreign_keys="Connector.user_id")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")
    agent_memories: Mapped[list["AgentMemory"]] = relationship(back_populates="user")


class LLM(Base):
    """LLM provider configurations."""
    
    __tablename__ = "llms"
    
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    api_key: Mapped[str | None] = mapped_column(String)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    assistants: Mapped[list["Assistant"]] = relationship(back_populates="llm")


class EmbeddingModel(Base):
    """Embedding model configurations (cluster-wide)."""
    
    __tablename__ = "embedding_models"
    
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    model_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class Assistant(Base):
    """AI assistant configurations with custom prompts."""
    
    __tablename__ = "assistants"
    
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    llm_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("llms.id"))
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    task_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    starter_messages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_priority: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    llm: Mapped[LLM | None] = relationship(back_populates="assistants")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="assistant")


class Connector(Base):
    """Data source connectors (Teams, Google Drive, etc.)."""
    
    __tablename__ = "connectors"
    
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    refresh_freq_minutes: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    scope_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    status_message: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    docs_analyzed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    user: Mapped[User] = relationship(back_populates="connectors", foreign_keys=[user_id])
    documents: Mapped[list["Document"]] = relationship(back_populates="connector")


class Document(Base):
    """Documents ingested from connectors."""
    
    __tablename__ = "documents"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("documents.id"))
    connector_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("connectors.id"), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    original_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(100))
    signature: Mapped[str | None] = mapped_column(Text)
    chunking_session: Mapped[str | None] = mapped_column(Text)  # UUID stored as text
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    status_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    
    connector: Mapped[Connector] = relationship(back_populates="documents")
    parent: Mapped["Document | None"] = relationship(remote_side=[id])
    message_documents: Mapped[list["ChatMessageDocument"]] = relationship(back_populates="document")


class ChatSession(Base):
    """Chat sessions between users and assistants."""
    
    __tablename__ = "chat_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assistant_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("assistants.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="New Chat")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    deleted_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    user: Mapped[User] = relationship(back_populates="chat_sessions")
    assistant: Mapped[Assistant] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual messages within chat sessions."""
    
    __tablename__ = "chat_messages"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("chat_messages.id"))
    rephrased_query: Mapped[str | None] = mapped_column(Text)
    retrieval_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tool_calls: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    
    session: Mapped[ChatSession] = relationship(back_populates="messages")
    parent_message: Mapped["ChatMessage | None"] = relationship(remote_side=[id])
    feedbacks: Mapped[list["ChatMessageFeedback"]] = relationship(back_populates="message", cascade="all, delete-orphan")
    message_documents: Mapped[list["ChatMessageDocument"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class ChatMessageFeedback(Base):
    """User feedback on assistant messages."""
    
    __tablename__ = "chat_message_feedbacks"
    __table_args__ = (
        UniqueConstraint("chat_message_id", "user_id", name="uq_feedback_message_user"),
    )
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    is_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feedback_text: Mapped[str | None] = mapped_column(Text)
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    
    message: Mapped[ChatMessage] = relationship(back_populates="feedbacks")


class ChatMessageDocument(Base):
    """Documents cited in chat messages."""
    
    __tablename__ = "chat_message_documents"
    __table_args__ = (
        UniqueConstraint("chat_message_id", "document_id", "chunk_id", name="uq_message_document_chunk"),
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    
    message: Mapped[ChatMessage] = relationship(back_populates="message_documents")
    document: Mapped[Document] = relationship(back_populates="message_documents")


class AgentMemory(Base):
    """Long-term agent memory for personalization."""
    
    __tablename__ = "agent_memories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_id: Mapped[str | None] = mapped_column(Text)
    importance_score: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    source_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chat_sessions.id"))
    creation_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    user_id_last_update: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    
    user: Mapped[User] = relationship(back_populates="agent_memories")
