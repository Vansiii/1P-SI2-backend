"""
Core database configuration with improved connection handling and retry logic.
"""
import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

logger = logging.getLogger(__name__)

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create database engine with improved configuration."""
    global engine

    if engine is None:
        settings = get_settings()
        database_url = settings.sqlalchemy_database_url
        
        engine = create_async_engine(
            database_url,
            pool_pre_ping=True,  # Test connections before using them
            pool_size=settings.db_pool_size,  # Number of connections to maintain in the pool
            max_overflow=settings.db_max_overflow,  # Additional connections beyond pool_size
            pool_timeout=settings.db_pool_timeout,  # Seconds to wait for a connection
            pool_recycle=settings.db_pool_recycle,  # Recycle connections after this many seconds
            echo=False,  # Disable SQL query logging for cleaner output
            connect_args={
                "server_settings": {
                    "application_name": "1P-SI2-Backend",
                    "statement_timeout": "30000",  # 30 seconds timeout for queries
                },
                "command_timeout": 30,  # 30 seconds timeout for commands
                "timeout": 30,  # Connection timeout
                "statement_cache_size": 0,  # Disable prepared statements for pgbouncer transaction mode
            },
        )
        
        logger.info(
            "Database engine created",
            extra={
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
                "pool_recycle": settings.db_pool_recycle,
            }
        )

    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create session factory."""
    global session_factory

    if session_factory is None:
        session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias para uso en tareas programadas
async_session_maker = get_session_factory

# Alias para compatibilidad con código existente
get_db = get_db_session


async def test_database_connection(max_retries: int = 3) -> None:
    """Test database connection with retry logic."""
    for attempt in range(max_retries):
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "Failed to connect to database after %d attempts: %s", 
                    max_retries,
                    str(exc)
                )
                raise RuntimeError(
                    "No se pudo conectar a la base de datos de Supabase. "
                    "Revisa DATABASE_URL en .env"
                ) from exc
            
            wait_time = 1  # Fixed 1 second wait
            logger.info(
                "Database connection attempt %d failed, retrying in %d second...",
                attempt + 1,
                wait_time
            )
            await asyncio.sleep(wait_time)


async def create_database_tables() -> None:
    """
    Create database tables. 
    WARNING: Only use in development! Use Alembic migrations in production.
    """
    settings = get_settings()
    
    if settings.is_production:
        logger.warning(
            "create_database_tables() called in production environment. "
            "This should not happen! Use Alembic migrations instead."
        )
        return
    
    # Import models to register tables in Base.metadata before create_all
    from ..models import (  # noqa: F401
        Administrator,
        AuditLog,
        Categoria,
        Client,
        Configuracion,
        Especialidad,
        EstadosServicio,
        Evidencia,
        EvidenciaAudio,
        EvidenciaImagen,
        HistorialServicio,
        Incidente,
        IncidentAIAnalysis,
        LoginAttempt,
        PasswordResetToken,
        RefreshToken,
        RevokedToken,
        Servicio,
        ServicioTaller,
        Technician,
        TechnicianEspecialidad,
        TwoFactorAuth,
        User,
        Vehiculo,
        Workshop,
        WorkshopSchedule,
    )
    
    from ..models.base import Base

    try:
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except SQLAlchemyError as exc:
        logger.error("Failed to create database tables", exc_info=True)
        raise RuntimeError("Error creating database tables") from exc


async def get_database_health() -> dict[str, Any]:
    """Get database health information."""
    try:
        async with get_engine().connect() as connection:
            # Test basic connectivity
            await connection.execute(text("SELECT 1"))
            
            # Get pool status
            pool = get_engine().pool
            
            return {
                "status": "healthy",
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
    except Exception as exc:
        logger.error("Database health check failed", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(exc),
        }


async def close_database_connection() -> None:
    """Close database connections and cleanup resources."""
    global engine
    global session_factory

    if engine is not None:
        logger.info("Closing database connections")
        await engine.dispose()

    engine = None
    session_factory = None
    logger.info("Database connections closed")