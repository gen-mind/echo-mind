"""
Database connection management for PostgreSQL.

Provides SQLAlchemy engine and session factory with connection pooling.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class DatabaseManager:
    """
    Manages database connections and sessions.
    
    Usage:
        db = DatabaseManager(database_url)
        await db.init()
        
        async with db.session() as session:
            # use session
            
        await db.close()
    """
    
    def __init__(self, database_url: str, echo: bool = False, pool_size: int = 5):
        """
        Initialize database manager.
        
        Args:
            database_url: PostgreSQL connection URL (postgresql+asyncpg://...)
            echo: If True, log all SQL statements
            pool_size: Connection pool size
        """
        self._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    async def init(self) -> None:
        """Initialize database (create tables if needed)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def close(self) -> None:
        """Close all database connections."""
        await self._engine.dispose()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session.
        
        Usage:
            async with db.session() as session:
                result = await session.execute(query)
        """
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    @property
    def engine(self):
        """Get the SQLAlchemy engine."""
        return self._engine


_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized. Call init_db() first.")
    return _db_manager


async def init_db(database_url: str, echo: bool = False) -> DatabaseManager:
    """
    Initialize the global database manager.
    
    Args:
        database_url: PostgreSQL connection URL
        echo: If True, log all SQL statements
    
    Returns:
        The initialized DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url, echo=echo)
    await _db_manager.init()
    return _db_manager


async def close_db() -> None:
    """Close the global database manager."""
    global _db_manager
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None
