"""
Session management router.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from .schemas import SessionListResponse
from .services import SessionService

router = APIRouter()


@router.get(
    "",
    response_model=SessionListResponse,
    summary="Get active sessions",
    description="Get all active sessions for the current user",
)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get all active sessions for the current user."""
    # Obtener el JTI actual desde el token del usuario
    current_jti = getattr(current_user, "_current_jti", None)
    if not current_jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo identificar la sesión actual"
        )
    
    sessions = await SessionService.get_active_sessions(
        db=db,
        user_id=current_user.id,
        current_jti=current_jti
    )
    
    # Separar sesión actual de otras sesiones
    current_session = next((s for s in sessions if s.is_current), None)
    other_sessions = [s for s in sessions if not s.is_current]
    
    if not current_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la sesión actual"
        )
    
    return SessionListResponse(
        current_session=current_session,
        other_sessions=other_sessions,
        total_sessions=len(sessions)
    )


@router.delete(
    "/{jti}",
    summary="Revoke specific session",
    description="Revoke a specific session by JTI",
)
async def revoke_session(
    jti: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Revoke a specific session."""
    current_jti = getattr(current_user, "_current_jti", None)
    if not current_jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo identificar la sesión actual"
        )
    
    success = await SessionService.revoke_session(
        db=db,
        user_id=current_user.id,
        jti=jti,
        current_jti=current_jti
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada o ya revocada"
        )
    
    return {"message": "Sesión cerrada exitosamente"}


@router.delete(
    "",
    summary="Revoke all other sessions",
    description="Revoke all sessions except the current one",
)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Revoke all sessions except the current one."""
    current_jti = getattr(current_user, "_current_jti", None)
    if not current_jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo identificar la sesión actual"
        )
    
    count = await SessionService.revoke_all_sessions(
        db=db,
        user_id=current_user.id,
        current_jti=current_jti
    )
    
    return {
        "message": f"Se cerraron {count} sesiones exitosamente",
        "revoked_count": count
    }
