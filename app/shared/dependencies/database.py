"""
Database dependencies for shared use.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session for use outside of FastAPI dependencies.
    Useful for background tasks, middleware, etc.
    """
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()