"""
Chat service for retrieval-augmented generation.

Orchestrates:
1. Query embedding via Embedder gRPC
2. Vector similarity search via Qdrant
3. Context assembly with retrieved documents
4. LLM completion with streaming
5. Message persistence to database
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.logic.embedder_client import EmbedderClient
from api.logic.exceptions import NotFoundError, ServiceUnavailableError
from api.logic.llm_client import ChatMessage as LLMMessage
from api.logic.llm_client import LLMClient, LLMConfig
from api.logic.permissions import PermissionChecker
from echomind_lib.db.models import Assistant as AssistantORM
from echomind_lib.db.models import ChatMessage as ChatMessageORM
from echomind_lib.db.models import ChatMessageDocument as ChatMessageDocumentORM
from echomind_lib.db.models import ChatSession as ChatSessionORM
from echomind_lib.db.models import Document as DocumentORM
from echomind_lib.db.qdrant import QdrantDB

if TYPE_CHECKING:
    from echomind_lib.helpers.auth import TokenUser

logger = logging.getLogger(__name__)


@dataclass
class RetrievedSource:
    """A document chunk retrieved for context."""

    document_id: int
    chunk_id: str
    score: float
    title: str
    content: str


@dataclass
class ChatResult:
    """Result of chat completion."""

    message_id: int
    content: str
    token_count: int
    sources: list[RetrievedSource]


class ChatService:
    """
    Service for retrieval-augmented chat generation.

    Orchestrates the full RAG pipeline:
    1. Embed user query
    2. Search Qdrant for relevant chunks
    3. Build prompt with context
    4. Stream LLM completion
    5. Persist message and sources

    Attributes:
        db: Database session.
        qdrant: Qdrant vector database client.
        embedder: Embedder gRPC client.
        llm: LLM HTTP client.
    """

    def __init__(
        self,
        db: AsyncSession,
        qdrant: QdrantDB,
        embedder: EmbedderClient,
        llm: LLMClient,
    ) -> None:
        """
        Initialize chat service.

        Args:
            db: Async database session.
            qdrant: Qdrant client for vector search.
            embedder: Embedder client for query embedding.
            llm: LLM client for generation.
        """
        self._db = db
        self._qdrant = qdrant
        self._embedder = embedder
        self._llm = llm
        self._permissions = PermissionChecker(db)

    async def get_session(
        self,
        session_id: int,
        user: "TokenUser",
    ) -> ChatSessionORM:
        """
        Get chat session with ownership verification.

        Args:
            session_id: Chat session ID.
            user: Authenticated user.

        Returns:
            ChatSessionORM with assistant loaded.

        Raises:
            NotFoundError: If session not found or not owned by user.
        """
        result = await self._db.execute(
            select(ChatSessionORM)
            .options(selectinload(ChatSessionORM.assistant).selectinload(AssistantORM.llm))
            .where(ChatSessionORM.id == session_id)
            .where(ChatSessionORM.deleted_date.is_(None))
        )
        session = result.scalar_one_or_none()

        if not session or session.user_id != user.id:
            raise NotFoundError("Chat session", session_id)

        return session

    async def retrieve_context(
        self,
        query: str,
        user: "TokenUser",
        limit: int = 5,
        min_score: float = 0.5,
    ) -> list[RetrievedSource]:
        """
        Retrieve relevant document chunks for query.

        Args:
            query: User's search query.
            user: Authenticated user (for collection access).
            limit: Maximum chunks to retrieve.
            min_score: Minimum similarity score threshold.

        Returns:
            List of retrieved sources sorted by relevance.

        Raises:
            ServiceUnavailableError: If Embedder or Qdrant unavailable.
        """
        # Get collections user can search
        collections = await self._permissions.get_search_collections(user)
        if not collections:
            logger.info("📭 No searchable collections for user %d", user.id)
            return []

        # Embed query
        try:
            query_vector = await self._embedder.embed_query(query)
        except Exception as e:
            logger.error("❌ Failed to embed query: %s", e)
            raise ServiceUnavailableError("Embedder") from e

        # Search each collection
        all_results: list[dict[str, Any]] = []
        for collection in collections:
            try:
                results = await self._qdrant.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=min_score,
                )
                for r in results:
                    r["collection"] = collection
                all_results.extend(results)
            except Exception as e:
                logger.warning(
                    "⚠️ Search failed for collection %s: %s",
                    collection,
                    e,
                )
                continue

        # Sort by score and take top results
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:limit]

        # Convert to sources
        sources: list[RetrievedSource] = []
        for result in top_results:
            payload = result.get("payload", {})
            sources.append(
                RetrievedSource(
                    document_id=payload.get("document_id", 0),
                    chunk_id=str(result.get("id", "")),
                    score=result.get("score", 0.0),
                    title=payload.get("title", "Unknown"),
                    content=payload.get("text", ""),
                )
            )

        logger.info(
            "🔍 Retrieved %d sources across %d collections for user %d",
            len(sources),
            len(collections),
            user.id,
        )

        return sources

    async def stream_response(
        self,
        session: ChatSessionORM,
        query: str,
        sources: list[RetrievedSource],
        user: "TokenUser",
    ) -> AsyncIterator[str]:
        """
        Stream LLM response with context.

        Args:
            session: Chat session with assistant configuration.
            query: User's query.
            sources: Retrieved context sources.
            user: Authenticated user.

        Yields:
            String tokens as they are generated.

        Raises:
            ServiceUnavailableError: If LLM unavailable.
            NotFoundError: If assistant has no LLM configured.
        """
        assistant = session.assistant
        if not assistant.llm:
            logger.error("❌ Assistant %d has no LLM configured", assistant.id)
            raise NotFoundError("LLM configuration", assistant.id)

        llm = assistant.llm

        # Build LLM config
        config = LLMConfig(
            provider=llm.provider,
            endpoint=llm.endpoint,
            model_id=llm.model_id,
            api_key=llm.api_key,
            max_tokens=llm.max_tokens,
            temperature=float(llm.temperature),
        )

        # Build messages with context
        messages = self._build_prompt_messages(
            assistant=assistant,
            query=query,
            sources=sources,
        )

        # Stream tokens
        async for token in self._llm.stream_completion(config, messages):
            yield token

    def _build_prompt_messages(
        self,
        assistant: AssistantORM,
        query: str,
        sources: list[RetrievedSource],
    ) -> list[LLMMessage]:
        """
        Build prompt messages with RAG context.

        Args:
            assistant: Assistant configuration.
            query: User's query.
            sources: Retrieved context sources.

        Returns:
            List of messages for LLM.
        """
        messages: list[LLMMessage] = []

        # System prompt
        system_content = assistant.system_prompt
        if sources:
            context_text = self._format_context(sources)
            system_content = f"{system_content}\n\n{context_text}"

        messages.append(LLMMessage(role="system", content=system_content))

        # Task prompt (if any)
        if assistant.task_prompt:
            messages.append(LLMMessage(role="user", content=assistant.task_prompt))

        # User query
        messages.append(LLMMessage(role="user", content=query))

        return messages

    def _format_context(self, sources: list[RetrievedSource]) -> str:
        """
        Format retrieved sources as context for LLM.

        Args:
            sources: Retrieved document chunks.

        Returns:
            Formatted context string.
        """
        if not sources:
            return ""

        context_parts = ["## Relevant Context\n"]
        context_parts.append(
            "Use the following information to answer the user's question. "
            "Cite sources using [Source N] notation.\n"
        )

        for i, source in enumerate(sources, 1):
            context_parts.append(f"\n### [Source {i}]: {source.title}")
            context_parts.append(f"Relevance: {source.score:.2f}")
            context_parts.append(source.content)

        return "\n".join(context_parts)

    async def save_user_message(
        self,
        session_id: int,
        content: str,
        rephrased_query: str | None = None,
    ) -> ChatMessageORM:
        """
        Save user message to database.

        Args:
            session_id: Chat session ID.
            content: Message content.
            rephrased_query: Optional rephrased query.

        Returns:
            Created ChatMessageORM.
        """
        message = ChatMessageORM(
            chat_session_id=session_id,
            role="user",
            content=content,
            token_count=len(content.split()),  # Rough estimate
            rephrased_query=rephrased_query,
            creation_date=datetime.now(timezone.utc),
        )
        self._db.add(message)
        await self._db.flush()
        await self._db.refresh(message)

        logger.info("💬 Saved user message %d", message.id)
        return message

    async def save_assistant_message(
        self,
        session_id: int,
        content: str,
        sources: list[RetrievedSource],
        parent_message_id: int | None = None,
    ) -> ChatMessageORM:
        """
        Save assistant message with source citations.

        Args:
            session_id: Chat session ID.
            content: Generated response content.
            sources: Retrieved sources to link.
            parent_message_id: Optional parent message ID.

        Returns:
            Created ChatMessageORM.
        """
        message = ChatMessageORM(
            chat_session_id=session_id,
            role="assistant",
            content=content,
            token_count=len(content.split()),  # Rough estimate
            parent_message_id=parent_message_id,
            retrieval_context={"source_count": len(sources)},
            creation_date=datetime.now(timezone.utc),
        )
        self._db.add(message)
        await self._db.flush()
        await self._db.refresh(message)

        # Link source documents
        for source in sources:
            doc_link = ChatMessageDocumentORM(
                chat_message_id=message.id,
                document_id=source.document_id,
                chunk_id=source.chunk_id,
                relevance_score=source.score,
                creation_date=datetime.now(timezone.utc),
            )
            self._db.add(doc_link)

        await self._db.flush()

        # Update session stats
        await self._update_session_stats(session_id)

        logger.info(
            "🤖 Saved assistant message %d with %d sources",
            message.id,
            len(sources),
        )
        return message

    async def _update_session_stats(self, session_id: int) -> None:
        """Update session message count and timestamp."""
        result = await self._db.execute(
            select(ChatSessionORM).where(ChatSessionORM.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.message_count = (session.message_count or 0) + 1
            session.last_message_at = datetime.now(timezone.utc)
            session.last_update = datetime.now(timezone.utc)

    async def get_document_titles(
        self,
        document_ids: list[int],
    ) -> dict[int, str]:
        """
        Get document titles by IDs.

        Args:
            document_ids: List of document IDs.

        Returns:
            Dict mapping document ID to title.
        """
        if not document_ids:
            return {}

        result = await self._db.execute(
            select(DocumentORM.id, DocumentORM.title).where(
                DocumentORM.id.in_(document_ids)
            )
        )
        return {row.id: row.title for row in result.all()}
