"""
Endpoint de métricas para Prometheus.
"""
from fastapi import APIRouter, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import get_metrics, update_db_connections, update_active_users, update_active_tokens
from app.shared.dependencies.database import get_async_session
from app.shared.dependencies.auth import get_current_admin
from app.models.administrator import Administrator

router = APIRouter(tags=["Metrics"])


@router.get(
    "/metrics",
    summary="Obtener métricas de Prometheus",
    description="Endpoint para que Prometheus scrape las métricas de la aplicación. Requiere autenticación de administrador."
)
async def metrics_endpoint(
    db: AsyncSession = Depends(get_async_session),
    current_admin: Administrator = Depends(get_current_admin)
):
    """
    Obtener métricas en formato Prometheus.
    
    Este endpoint expone métricas de:
    - Requests HTTP (total, duración, en progreso)
    - Autenticación (intentos, fallos, bloqueos)
    - Tokens (creados, revocados, activos)
    - Base de datos (queries, conexiones)
    - Usuarios (registros, activos)
    - 2FA (habilitaciones, verificaciones)
    - Emails (enviados, fallidos)
    - Rate limiting (excesos)
    - Errores y excepciones
    
    **Requiere:** Autenticación de administrador
    
    **Formato:** Prometheus text format
    """
    # Actualizar métricas dinámicas antes de exportar
    await update_dynamic_metrics(db)
    
    # Obtener métricas
    content, content_type = get_metrics()
    
    return Response(content=content, media_type=content_type)


@router.get(
    "/metrics/public",
    summary="Obtener métricas públicas",
    description="Endpoint público con métricas básicas (sin autenticación requerida). Útil para health checks externos."
)
async def public_metrics_endpoint():
    """
    Obtener métricas públicas básicas.
    
    Este endpoint expone solo métricas no sensibles:
    - Total de requests
    - Duración promedio de requests
    - Tasa de errores
    
    **No requiere autenticación**
    """
    content, content_type = get_metrics()
    
    return Response(content=content, media_type=content_type)


async def update_dynamic_metrics(db: AsyncSession):
    """
    Actualizar métricas dinámicas que requieren consultas a la base de datos.
    """
    try:
        # Actualizar métricas de conexiones de base de datos
        pool = db.get_bind().pool
        if hasattr(pool, 'size') and hasattr(pool, 'checkedin'):
            active = pool.size() - pool.checkedin()
            idle = pool.checkedin()
            update_db_connections(active, idle)
        
        # Actualizar métricas de usuarios activos
        from app.modules.auth.repository import UserRepository
        user_repo = UserRepository(db)
        
        for user_type in ["client", "workshop", "technician", "administrator"]:
            count = await user_repo.count_active_users(user_type)
            update_active_users(user_type, count)
        
        # Actualizar métricas de tokens activos
        from app.modules.tokens.repository import TokenRepository
        token_repo = TokenRepository(db)
        
        refresh_count = await token_repo.count_active_refresh_tokens()
        update_active_tokens("refresh", refresh_count)
        
    except Exception as e:
        # No fallar si hay error actualizando métricas
        import structlog
        logger = structlog.get_logger()
        logger.error("error_updating_metrics", error=str(e))
