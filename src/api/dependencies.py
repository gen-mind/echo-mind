"""
FastAPI dependency injection.

Provides dependencies for database sessions, authentication, and services.
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from echomind_lib.db.connection import get_db_manager
from echomind_lib.helpers.auth import (
    TokenUser,
    extract_bearer_token,
    get_jwt_validator,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session.
    
    Usage:
        @app.get("/items")
        async def get_items(db: DbSession):
            ...
    """
    db = get_db_manager()
    async with db.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> TokenUser:
    """
    Get the current authenticated user from JWT token.
    
    Usage:
        @app.get("/me")
        async def get_me(user: CurrentUser):
            return user
    """
    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        validator = get_jwt_validator()
        return validator.validate_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentUser = Annotated[TokenUser, Depends(get_current_user)]


async def get_current_user_optional(
    authorization: Annotated[str | None, Header()] = None,
) -> TokenUser | None:
    """
    Get the current user if authenticated, None otherwise.
    
    Usage:
        @app.get("/public")
        async def public_endpoint(user: OptionalUser):
            if user:
                # authenticated
            else:
                # anonymous
    """
    token = extract_bearer_token(authorization)
    if not token:
        return None
    
    try:
        validator = get_jwt_validator()
        return validator.validate_token(token)
    except Exception:
        return None


OptionalUser = Annotated[TokenUser | None, Depends(get_current_user_optional)]


def require_role(role: str):
    """
    Dependency factory to require a specific role.
    
    Usage:
        @app.get("/admin", dependencies=[Depends(require_role("admin"))])
        async def admin_only():
            ...
    """
    async def check_role(user: CurrentUser) -> TokenUser:
        if role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return user
    
    return check_role


def require_any_role(*roles: str):
    """
    Dependency factory to require any of the specified roles.
    
    Usage:
        @app.get("/staff", dependencies=[Depends(require_any_role("admin", "moderator"))])
        async def staff_only():
            ...
    """
    async def check_roles(user: CurrentUser) -> TokenUser:
        if not any(r in user.roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of roles {roles} required",
            )
        return user
    
    return check_roles


AdminUser = Annotated[TokenUser, Depends(require_role("admin"))]
