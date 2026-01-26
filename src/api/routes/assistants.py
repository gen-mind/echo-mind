"""Assistant management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.dependencies import CurrentUser, DbSession
from echomind_lib.db.models import Assistant as AssistantORM
from echomind_lib.models.public import (
    Assistant,
    CreateAssistantRequest,
    ListAssistantsResponse,
    UpdateAssistantRequest,
)

router = APIRouter()


@router.get("", response_model=ListAssistantsResponse)
async def list_assistants(
    user: CurrentUser,
    db: DbSession,
    page: int = 1,
    limit: int = 20,
    is_visible: bool | None = None,
) -> ListAssistantsResponse:
    """
    List all assistants.

    Args:
        user: The authenticated user.
        db: Database session.
        page: Page number for pagination.
        limit: Number of items per page.
        is_visible: Optional filter by visibility.

    Returns:
        ListAssistantsResponse: Paginated list of assistants.
    """
    query = select(AssistantORM).where(AssistantORM.deleted_date.is_(None))
    
    if is_visible is not None:
        query = query.where(AssistantORM.is_visible == is_visible)
    
    query = query.order_by(AssistantORM.display_priority, AssistantORM.name)
    
    # Count total
    count_query = select(AssistantORM.id).where(AssistantORM.deleted_date.is_(None))
    if is_visible is not None:
        count_query = count_query.where(AssistantORM.is_visible == is_visible)
    # Paginate
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    db_assistants = result.scalars().all()
    
    assistants = [Assistant.model_validate(a, from_attributes=True) for a in db_assistants]
    
    return ListAssistantsResponse(assistants=assistants)


@router.post("", response_model=Assistant, status_code=status.HTTP_201_CREATED)
async def create_assistant(
    data: CreateAssistantRequest,
    user: CurrentUser,
    db: DbSession,
) -> Assistant:
    """
    Create a new assistant.

    Args:
        data: The assistant creation data.
        user: The authenticated user.
        db: Database session.

    Returns:
        Assistant: The created assistant.
    """
    assistant = AssistantORM(
        name=data.name,
        description=data.description,
        llm_id=data.llm_id,
        system_prompt=data.system_prompt,
        task_prompt=data.task_prompt,
        starter_messages=data.starter_messages,
        is_default=data.is_default,
        is_visible=data.is_visible,
        display_priority=data.display_priority,
        created_by=user.id,
        user_id_last_update=user.id,
    )
    
    db.add(assistant)
    await db.flush()
    await db.refresh(assistant)
    
    return Assistant.model_validate(assistant, from_attributes=True)


@router.get("/{assistant_id}", response_model=Assistant)
async def get_assistant(
    assistant_id: int,
    user: CurrentUser,
    db: DbSession,
) -> Assistant:
    """
    Get an assistant by ID.

    Args:
        assistant_id: The ID of the assistant to retrieve.
        user: The authenticated user.
        db: Database session.

    Returns:
        Assistant: The requested assistant.

    Raises:
        HTTPException: 404 if assistant not found.
    """
    result = await db.execute(
        select(AssistantORM)
        .where(AssistantORM.id == assistant_id)
        .where(AssistantORM.deleted_date.is_(None))
    )
    db_assistant = result.scalar_one_or_none()
    
    if not db_assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant not found",
        )
    
    return Assistant.model_validate(db_assistant, from_attributes=True)


@router.put("/{assistant_id}", response_model=Assistant)
async def update_assistant(
    assistant_id: int,
    data: UpdateAssistantRequest,
    user: CurrentUser,
    db: DbSession,
) -> Assistant:
    """
    Update an assistant.

    Args:
        assistant_id: The ID of the assistant to update.
        data: The fields to update.
        user: The authenticated user.
        db: Database session.

    Returns:
        Assistant: The updated assistant.

    Raises:
        HTTPException: 404 if assistant not found.
    """
    result = await db.execute(
        select(AssistantORM)
        .where(AssistantORM.id == assistant_id)
        .where(AssistantORM.deleted_date.is_(None))
    )
    db_assistant = result.scalar_one_or_none()
    
    if not db_assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant not found",
        )
    
    if data.name:
        db_assistant.name = data.name
    if data.description:
        db_assistant.description = data.description
    if data.llm_id:
        db_assistant.llm_id = data.llm_id
    if data.system_prompt:
        db_assistant.system_prompt = data.system_prompt
    if data.task_prompt:
        db_assistant.task_prompt = data.task_prompt
    if data.starter_messages:
        db_assistant.starter_messages = data.starter_messages
    if data.is_default is not None:
        db_assistant.is_default = data.is_default
    if data.is_visible is not None:
        db_assistant.is_visible = data.is_visible
    if data.display_priority is not None:
        db_assistant.display_priority = data.display_priority
    
    db_assistant.user_id_last_update = user.id
    
    return Assistant.model_validate(db_assistant, from_attributes=True)


@router.delete("/{assistant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assistant(
    assistant_id: int,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Delete an assistant (soft delete).

    Args:
        assistant_id: The ID of the assistant to delete.
        user: The authenticated user.
        db: Database session.

    Raises:
        HTTPException: 404 if assistant not found.
    """
    result = await db.execute(
        select(AssistantORM)
        .where(AssistantORM.id == assistant_id)
        .where(AssistantORM.deleted_date.is_(None))
    )
    db_assistant = result.scalar_one_or_none()
    
    if not db_assistant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant not found",
        )
    
    db_assistant.deleted_date = datetime.now(timezone.utc)
    db_assistant.user_id_last_update = user.id
