"""
Router para endpoints administrativos de incidentes.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session as get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.responses import success_response
from ...models.user import User
from .admin_service import IncidentAdminService
from .admin_schemas import IncidentDetailAdminResponse

router = APIRouter(prefix="/incidentes/admin", tags=["Incidentes - Admin"])


@router.get(
    "/{incident_id}/detail"
)
async def get_incident_admin_detail(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtener detalles completos de un incidente para administradores.
    
    Incluye:
    - Información del incidente
    - Historial de asignaciones
    - Rechazos de talleres
    - Intentos de asignación sin respuesta
    - Historial de estados
    
    **Permisos:** Requiere ser administrador
    """
    # Verificar que sea admin
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden acceder a esta información"
        )
    
    service = IncidentAdminService(db)
    
    # Las excepciones AppException (como NotFoundException) se propagan
    # al middleware ErrorHandlingMiddleware que las maneja correctamente
    detail = await service.get_incident_admin_detail(incident_id)
    return success_response(data=detail)


@router.post(
    "/technicians/reset-stuck",
    summary="Resetear técnicos atascados",
    description=(
        "Libera técnicos marcados como is_on_duty=True pero que no tienen "
        "un incidente activo (en_proceso o en_sitio). Útil para corregir "
        "estados inconsistentes en la base de datos."
    ),
)
async def reset_stuck_technicians(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resetea técnicos atascados: is_on_duty=True sin incidente activo.
    Solo accesible por administradores.
    """
    if current_user.user_type not in ("admin", "administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden ejecutar esta operación",
        )

    from sqlalchemy import select, update, and_
    from ...models.technician import Technician
    from ...models.incidente import Incidente
    from datetime import datetime, UTC

    # Técnicos con is_on_duty=True
    result = await db.execute(
        select(Technician).where(
            and_(Technician.is_on_duty == True, Technician.is_active == True)
        )
    )
    on_duty_technicians = list(result.scalars().all())

    reset_ids = []
    for tech in on_duty_technicians:
        # Verificar si tiene incidente activo
        active_incident = await db.scalar(
            select(Incidente).where(
                and_(
                    Incidente.tecnico_id == tech.id,
                    Incidente.estado_actual.in_(["en_proceso", "en_sitio", "asignado"]),
                )
            )
        )
        if not active_incident:
            tech.is_on_duty = False
            tech.is_available = True
            tech.updated_at = datetime.now(UTC)
            reset_ids.append(tech.id)

    if reset_ids:
        await db.commit()

    return success_response(
        data={
            "reset_count": len(reset_ids),
            "reset_technician_ids": reset_ids,
            "checked_count": len(on_duty_technicians),
        },
        message=f"Se liberaron {len(reset_ids)} técnicos atascados de {len(on_duty_technicians)} revisados.",
    )
