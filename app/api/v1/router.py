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
from ...modules.incidentes.admin_router import router as incidentes_admin_router
from ...modules.files.router import router as files_router

# Import infrastructure endpoints (same level)
from . import health, metrics, websocket, diagnostics

# Import from modules
from ...modules.events.router import router as events_router
from ...modules.sync.router import router as sync_router
from ...modules.chat.router import router as chat_router
from ...modules.cancellation.router import router as cancellation_router
from ...modules.tracking.router import router as tracking_router
from ...modules.assignment.router import router as assignment_router
from ...modules.real_time.router import router as real_time_router
from ...modules.push_notifications.router import router as push_notifications_router
from ...modules.incident_states.router import router as incident_states_router
from ...modules.technician_management.router import router as technician_management_router
from ...modules.routing.router import router as routing_router
from ...modules.metrics.router import router as metrics_endpoints_router
from ...modules.metrics.timeseries_router import router as metrics_timeseries_router
from ...modules.especialidades.router import router as especialidades_router

# Import admin routers
from .admin import ai_analytics_router

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

# Incidentes admin routes
api_router.include_router(
    incidentes_admin_router,
    tags=["Incidentes - Admin"],
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

# WebSocket routes
api_router.include_router(
    websocket.router,
    tags=["WebSocket"],
)

# Diagnostics routes (database connection monitoring)
api_router.include_router(
    diagnostics.router,
    tags=["Diagnostics"],
)

# Events routes (missed events recovery)
api_router.include_router(
    events_router,
    tags=["Events"],
)

# Sync routes (offline queue synchronization)
api_router.include_router(
    sync_router,
    tags=["Sync"],
)

# Real-time API routes
api_router.include_router(
    real_time_router,
    prefix="/real-time",
    tags=["Real-time"],
)

# Push notification routes
api_router.include_router(
    push_notifications_router,
    prefix="/push",
    tags=["Push Notifications"],
)

# Assignment routes (includes automatic assignment + reassignment/admin endpoints)
api_router.include_router(
    assignment_router,
    tags=["Assignment"],
)

# Tracking routes
api_router.include_router(
    tracking_router,
    tags=["Tracking"],
)

# Chat routes
api_router.include_router(
    chat_router,
    tags=["Chat"],
)

# Cancellation routes
api_router.include_router(
    cancellation_router,
    tags=["Cancellation"],
)

# Incident state management routes
api_router.include_router(
    incident_states_router,
    tags=["Incident States"],
)

# Technician management routes
api_router.include_router(
    technician_management_router,
    tags=["Technician Management"],
)

# Routing and geocoding routes
api_router.include_router(
    routing_router,
    tags=["Routing & Geocoding"],
)

# Metrics and reporting routes
api_router.include_router(
    metrics_endpoints_router,
    tags=["Metrics & Reporting"],
)

# Metrics time series routes
api_router.include_router(
    metrics_timeseries_router,
    tags=["Metrics Time Series"],
)

# Especialidades routes
api_router.include_router(
    especialidades_router,
    tags=["Especialidades"],
)

# Admin AI Analytics routes
api_router.include_router(
    ai_analytics_router,
    prefix="/admin",
    tags=["Admin - AI Analytics"],
)

__all__ = ["api_router"]
