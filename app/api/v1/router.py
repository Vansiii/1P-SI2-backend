"""
Main API v1 router - imports routers from modules.
"""
from fastapi import APIRouter

# Import routers from modules
from ...modules.auth.router import router as auth_router
from ...modules.password.router import router as password_router
from ...modules.tokens.router import router as tokens_router
from ...modules.two_factor.router import router as two_factor_router
from ...modules.users.router import router as users_router
from ...modules.audit.router import router as audit_router
from ...modules.sessions.router import router as sessions_router
from ...modules.permissions.router import router as permissions_router
from ...modules.vehiculos.router import router as vehiculos_router
from ...modules.vehiculos.upload_router import router as vehiculos_upload_router
from ...modules.incidentes.router import router as incidentes_router
from ...modules.incidentes.upload_router import router as incidentes_upload_router
from ...modules.files.router import router as files_router

# Import infrastructure endpoints (same level)
from . import health, metrics

# Create main v1 router
api_router = APIRouter(prefix="/api/v1")

# Authentication routes
api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

# User management routes
api_router.include_router(
    users_router,
    prefix="/users",
    tags=["Users"],
)

# Token management routes
api_router.include_router(
    tokens_router,
    prefix="/tokens",
    tags=["Tokens"],
)

# Password management routes
api_router.include_router(
    password_router,
    prefix="/password",
    tags=["Password"],
)

# Two-factor authentication routes
api_router.include_router(
    two_factor_router,
    prefix="/2fa",
    tags=["Two Factor Authentication"],
)

# Audit routes
api_router.include_router(
    audit_router,
    prefix="/audit",
    tags=["Audit"],
)

# Session management routes
api_router.include_router(
    sessions_router,
    prefix="/sessions",
    tags=["Sessions"],
)

# Permissions management routes
api_router.include_router(
    permissions_router,
    prefix="/admin",
    tags=["Permissions Management"],
)

# Vehiculos routes
api_router.include_router(
    vehiculos_router,
    tags=["Vehículos"],
)

# Vehiculos upload routes
api_router.include_router(
    vehiculos_upload_router,
    tags=["Vehículos - Upload"],
)

# Incidentes routes
api_router.include_router(
    incidentes_router,
    tags=["Incidentes"],
)

# Incidentes upload routes
api_router.include_router(
    incidentes_upload_router,
    tags=["Incidentes - Upload"],
)

# Files management routes
api_router.include_router(
    files_router,
    tags=["Files"],
)

# Infrastructure endpoints
# Health check routes
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

# Metrics routes
api_router.include_router(
    metrics.router,
    tags=["Metrics"],
)

__all__ = ["api_router"]