from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings
from .models.base import Base

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global engine

    if engine is None:
        database_url = get_settings().sqlalchemy_database_url
        engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global session_factory

    if session_factory is None:
        session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def test_database_connection() -> None:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            "No se pudo conectar a la base de datos de Supabase. Revisa DATABASE_URL en backend/.env"
        ) from exc


async def create_database_tables() -> None:
    # Importa modelos para registrar tablas en Base.metadata antes de create_all.
    from .models import revoked_token, workshop_user  # noqa: F401

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_database_connection() -> None:
    global engine
    global session_factory

    if engine is not None:
        await engine.dispose()

    engine = None
    session_factory = None
