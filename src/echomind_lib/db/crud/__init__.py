"""
CRUD operations for all database entities.

Usage:
    from echomind_lib.db.crud import user_crud, assistant_crud, document_crud

    # Get user by ID
    user = await user_crud.get_by_id(session, user_id)

    # Get active assistants
    assistants = await assistant_crud.get_multi_active(session, limit=10)

    # Create document
    doc = await document_crud.create(session, obj_in={...})
"""

from echomind_lib.db.crud.agent_memory import AgentMemoryCRUD, agent_memory_crud
from echomind_lib.db.crud.assistant import AssistantCRUD, assistant_crud
from echomind_lib.db.crud.base import CRUDBase, SoftDeleteMixin
from echomind_lib.db.crud.chat_message import (
    ChatMessageCRUD,
    ChatMessageDocumentCRUD,
    ChatMessageFeedbackCRUD,
    chat_message_crud,
    chat_message_document_crud,
    chat_message_feedback_crud,
)
from echomind_lib.db.crud.chat_session import ChatSessionCRUD, chat_session_crud
from echomind_lib.db.crud.connector import ConnectorCRUD, connector_crud
from echomind_lib.db.crud.document import DocumentCRUD, document_crud
from echomind_lib.db.crud.embedding_model import EmbeddingModelCRUD, embedding_model_crud
from echomind_lib.db.crud.llm import LLMCRUD, llm_crud
from echomind_lib.db.crud.user import UserCRUD, user_crud

__all__ = [
    # Base classes
    "CRUDBase",
    "SoftDeleteMixin",
    # CRUD classes
    "UserCRUD",
    "AssistantCRUD",
    "LLMCRUD",
    "EmbeddingModelCRUD",
    "ConnectorCRUD",
    "DocumentCRUD",
    "ChatSessionCRUD",
    "ChatMessageCRUD",
    "ChatMessageFeedbackCRUD",
    "ChatMessageDocumentCRUD",
    "AgentMemoryCRUD",
    # Singleton instances
    "user_crud",
    "assistant_crud",
    "llm_crud",
    "embedding_model_crud",
    "connector_crud",
    "document_crud",
    "chat_session_crud",
    "chat_message_crud",
    "chat_message_feedback_crud",
    "chat_message_document_crud",
    "agent_memory_crud",
]
