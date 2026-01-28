"""Connector management endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.converters import orm_to_connector
from api.dependencies import CurrentUser, DbSession, NatsPublisher
from api.logic.connector_service import ConnectorService
from api.logic.exceptions import NotFoundError
from echomind_lib.models.public import (
    Connector,
    CreateConnectorRequest,
    ListConnectorsResponse,
    UpdateConnectorRequest,
)

router = APIRouter()


class TriggerSyncResponse(BaseModel):
    """Response model for triggering a sync."""

    success: bool
    message: str


class ConnectorStatusResponse(BaseModel):
    """Response model for connector status."""

    status: str
    status_message: str | None
    last_sync_at: datetime | None
    docs_analyzed: int
    docs_pending: int


@router.get("", response_model=ListConnectorsResponse)
async def list_connectors(
    user: CurrentUser,
    db: DbSession,
    page: int = 1,
    limit: int = 20,
    connector_type: str | None = None,
    connector_status: str | None = None,
) -> ListConnectorsResponse:
    """
    List all connectors for the current user.

    Args:
        user: The authenticated user.
        db: Database session.
        page: Page number for pagination.
        limit: Number of items per page.
        connector_type: Optional filter by connector type.
        connector_status: Optional filter by status.

    Returns:
        ListConnectorsResponse: Paginated list of connectors.
    """
    from sqlalchemy import select

    from echomind_lib.db.models import Connector as ConnectorORM

    query = select(ConnectorORM).where(
        ConnectorORM.user_id == user.id,
        ConnectorORM.deleted_date.is_(None),
    )

    if connector_type:
        query = query.where(ConnectorORM.type == connector_type)
    if connector_status:
        query = query.where(ConnectorORM.status == connector_status)

    query = query.order_by(ConnectorORM.name)

    # Paginate
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    db_connectors = result.scalars().all()

    connectors = [orm_to_connector(c) for c in db_connectors]

    return ListConnectorsResponse(connectors=connectors)


@router.post("", response_model=Connector, status_code=status.HTTP_201_CREATED)
async def create_connector(
    data: CreateConnectorRequest,
    user: CurrentUser,
    db: DbSession,
    nats: NatsPublisher,
) -> Connector:
    """
    Create a new connector and trigger initial sync.

    Args:
        data: The connector creation data.
        user: The authenticated user.
        db: Database session.
        nats: NATS publisher for sync messages.

    Returns:
        Connector: The created connector.
    """
    service = ConnectorService(db, nats)

    connector = await service.create_connector(
        name=data.name,
        connector_type=data.type.name if data.type else "unspecified",
        user_id=user.id,
        config=data.config,
        refresh_freq_minutes=data.refresh_freq_minutes,
        scope=data.scope.name if data.scope else None,
        scope_id=data.scope_id,
        trigger_sync=True,  # Publish NATS message for initial sync
    )

    return orm_to_connector(connector)


@router.get("/{connector_id}", response_model=Connector)
async def get_connector(
    connector_id: int,
    user: CurrentUser,
    db: DbSession,
) -> Connector:
    """
    Get a connector by ID.

    Args:
        connector_id: The ID of the connector to retrieve.
        user: The authenticated user.
        db: Database session.

    Returns:
        Connector: The requested connector.

    Raises:
        HTTPException: 404 if connector not found.
    """
    service = ConnectorService(db)

    try:
        connector = await service.get_connector(connector_id, user.id)
        return orm_to_connector(connector)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )


@router.put("/{connector_id}", response_model=Connector)
async def update_connector(
    connector_id: int,
    data: UpdateConnectorRequest,
    user: CurrentUser,
    db: DbSession,
) -> Connector:
    """
    Update a connector.

    Args:
        connector_id: The ID of the connector to update.
        data: The fields to update.
        user: The authenticated user.
        db: Database session.

    Returns:
        Connector: The updated connector.

    Raises:
        HTTPException: 404 if connector not found.
    """
    service = ConnectorService(db)

    try:
        connector = await service.update_connector(
            connector_id=connector_id,
            user_id=user.id,
            name=data.name,
            config=data.config,
            refresh_freq_minutes=data.refresh_freq_minutes,
            scope=data.scope.name if data.scope and hasattr(data.scope, "name") else None,
            scope_id=data.scope_id,
        )
        return orm_to_connector(connector)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: int,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """
    Delete a connector (soft delete).

    Args:
        connector_id: The ID of the connector to delete.
        user: The authenticated user.
        db: Database session.

    Raises:
        HTTPException: 404 if connector not found.
    """
    service = ConnectorService(db)

    try:
        await service.delete_connector(connector_id, user.id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )


@router.post("/{connector_id}/sync", response_model=TriggerSyncResponse)
async def trigger_sync(
    connector_id: int,
    user: CurrentUser,
    db: DbSession,
    nats: NatsPublisher,
) -> TriggerSyncResponse:
    """
    Trigger a manual sync for a connector.

    Publishes a ConnectorSyncRequest message to NATS to start the sync process.

    Args:
        connector_id: The ID of the connector to sync.
        user: The authenticated user.
        db: Database session.
        nats: NATS publisher for sync messages.

    Returns:
        TriggerSyncResponse: Success status and message.

    Raises:
        HTTPException: 404 if connector not found.
    """
    service = ConnectorService(db, nats)

    try:
        success, message = await service.trigger_sync(connector_id, user.id)
        return TriggerSyncResponse(success=success, message=message)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )


@router.get("/{connector_id}/status", response_model=ConnectorStatusResponse)
async def get_connector_status(
    connector_id: int,
    user: CurrentUser,
    db: DbSession,
) -> ConnectorStatusResponse:
    """
    Get the sync status of a connector.

    Args:
        connector_id: The ID of the connector.
        user: The authenticated user.
        db: Database session.

    Returns:
        ConnectorStatusResponse: Status information.

    Raises:
        HTTPException: 404 if connector not found.
    """
    service = ConnectorService(db)

    try:
        status_info = await service.get_connector_status(connector_id, user.id)
        return ConnectorStatusResponse(**status_info)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )