from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.router import api_router
from .core import (
    close_database_connection,
    create_database_tables,
    get_settings,
    test_database_connection,
    configure_logging,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
)

# Configure logging first
configure_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await test_database_connection()
    if settings.environment == "development":
        await create_database_tables()
    yield
    # Shutdown
    await close_database_connection()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="MecánicoYa - API REST",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# Add middleware (order matters - first added is outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Include API router
app.include_router(api_router)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint with basic API information."""
    return {
        "message": "MecánicoYa - API REST",
        "version": settings.app_version,
        "docs": "/docs" if settings.environment != "production" else "disabled",
        "health": "/api/v1/health",
    }
