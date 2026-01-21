"""User management endpoints."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.dependencies import AdminUser, CurrentUser, DbSession
from echomind_lib.db.models import User as UserORM
from echomind_lib.models.public import (
    ListUsersResponse,
    UpdateUserRequest,
    User,
)

router = APIRouter()


@router.get("/me", response_model=User)
async def get_current_user_profile(
    user: CurrentUser,
    db: DbSession,
) -> User:
    """
    Get the current user's profile.

    Args:
        user: The authenticated user from JWT token.
        db: Database session.

    Returns:
        User: The current user's profile data.

    Raises:
        HTTPException: 404 if user not found in database.
    """
    result = await db.execute(select(UserORM).where(UserORM.id == user.id))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return User.model_validate(db_user, from_attributes=True)


@router.put("/me", response_model=User)
async def update_current_user_profile(
    updates: UpdateUserRequest,
    user: CurrentUser,
    db: DbSession,
) -> User:
    """
    Update the current user's profile.

    Args:
        updates: The fields to update.
        user: The authenticated user from JWT token.
        db: Database session.

    Returns:
        User: The updated user profile.

    Raises:
        HTTPException: 404 if user not found in database.
    """
    result = await db.execute(select(UserORM).where(UserORM.id == user.id))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if updates.first_name:
        db_user.first_name = updates.first_name
    if updates.last_name:
        db_user.last_name = updates.last_name
    if updates.preferences is not None:
        prefs = db_user.preferences.copy() if db_user.preferences else {}
        if updates.preferences.default_assistant_id:
            prefs["default_assistant_id"] = updates.preferences.default_assistant_id
        if updates.preferences.theme:
            prefs["theme"] = updates.preferences.theme
        db_user.preferences = prefs
    
    db_user.user_id_last_update = user.id
    
    return User.model_validate(db_user, from_attributes=True)


@router.get("", response_model=ListUsersResponse)
async def list_users(
    admin: AdminUser,
    db: DbSession,
    page: int = 1,
    limit: int = 20,
    is_active: bool | None = None,
) -> ListUsersResponse:
    """
    List all users (admin only).

    Args:
        admin: The authenticated admin user.
        db: Database session.
        page: Page number for pagination.
        limit: Number of items per page.
        is_active: Optional filter by active status.

    Returns:
        ListUsersResponse: Paginated list of users.
    """
    query = select(UserORM)
    
    if is_active is not None:
        query = query.where(UserORM.is_active == is_active)
    
    # Count total
    count_query = select(UserORM.id)
    if is_active is not None:
        count_query = count_query.where(UserORM.is_active == is_active)
    count_result = await db.execute(count_query)
    total = len(count_result.all())
    
    # Paginate
    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    db_users = result.scalars().all()
    
    users = [User.model_validate(u, from_attributes=True) for u in db_users]
    
    return ListUsersResponse(users=users)


@router.get("/{user_id}", response_model=User)
async def get_user_by_id(
    user_id: int,
    admin: AdminUser,
    db: DbSession,
) -> User:
    """
    Get a user by ID (admin only).

    Args:
        user_id: The ID of the user to retrieve.
        admin: The authenticated admin user.
        db: Database session.

    Returns:
        User: The requested user's data.

    Raises:
        HTTPException: 404 if user not found.
    """
    result = await db.execute(select(UserORM).where(UserORM.id == user_id))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return User.model_validate(db_user, from_attributes=True)
