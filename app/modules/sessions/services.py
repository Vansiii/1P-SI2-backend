from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.refresh_token import RefreshToken
from .schemas import SessionResponse


class SessionService:
    """Servicio para gestión de sesiones activas"""

    @staticmethod
    def _parse_user_agent(user_agent: str | None) -> tuple[str, str]:
        """Extrae información del dispositivo desde el user agent"""
        if not user_agent:
            return "Dispositivo desconocido", "desktop"
        
        ua_lower = user_agent.lower()
        
        # Detectar Flutter/Dart (aplicación móvil)
        if "dart" in ua_lower or "flutter" in ua_lower:
            # Es la app móvil
            device_type = "mobile"
            device_name = "Aplicación Móvil"
            
            # Intentar detectar el sistema operativo
            if "android" in ua_lower:
                device_name = "Android"
            elif "ios" in ua_lower or "iphone" in ua_lower:
                device_name = "iPhone"
            elif "ipad" in ua_lower:
                device_name = "iPad"
                device_type = "tablet"
            
            return device_name, device_type
        
        # Detectar tipo de dispositivo para navegadores web
        if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
            device_type = "mobile"
        elif "tablet" in ua_lower or "ipad" in ua_lower:
            device_type = "tablet"
        else:
            device_type = "desktop"
        
        # Detectar navegador
        if "chrome" in ua_lower and "edg" not in ua_lower:
            device_name = "Chrome"
        elif "firefox" in ua_lower:
            device_name = "Firefox"
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            device_name = "Safari"
        elif "edg" in ua_lower:
            device_name = "Edge"
        elif "opera" in ua_lower or "opr" in ua_lower:
            device_name = "Opera"
        else:
            device_name = "Navegador"
        
        # Agregar sistema operativo para navegadores
        if "windows" in ua_lower:
            device_name += " en Windows"
        elif "mac" in ua_lower and "iphone" not in ua_lower and "ipad" not in ua_lower:
            device_name += " en Mac"
        elif "linux" in ua_lower and "android" not in ua_lower:
            device_name += " en Linux"
        elif "android" in ua_lower:
            device_name = "Android"
        
        return device_name, device_type

    @staticmethod
    def _get_location_from_ip(ip_address: str | None) -> str:
        """Obtiene ubicación aproximada desde IP (simplificado)"""
        if not ip_address:
            return "Ubicación desconocida"
        
        # IPs locales
        if ip_address.startswith("127.") or ip_address.startswith("192.168.") or ip_address.startswith("10."):
            return "Red local"
        
        # TODO: Integrar con servicio de geolocalización real como:
        # - ipapi.co
        # - ip-api.com
        # - geoip2 (MaxMind)
        
        # Por ahora retorna ubicación genérica
        return "Bolivia"

    @staticmethod
    async def get_active_sessions(
        db: AsyncSession,
        user_id: int,
        current_jti: str
    ) -> list[SessionResponse]:
        """Obtiene todas las sesiones activas de un usuario"""
        now = datetime.now(timezone.utc)
        
        # Buscar todos los refresh tokens activos
        result = await db.execute(
            select(RefreshToken)
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now
                )
            )
            .order_by(RefreshToken.created_at.desc())
        )
        
        tokens = result.scalars().all()
        
        sessions = []
        for token in tokens:
            device_name, device_type = SessionService._parse_user_agent(token.user_agent)
            location = SessionService._get_location_from_ip(token.ip_address)
            
            sessions.append(SessionResponse(
                jti=token.jti,
                device_name=device_name,
                device_type=device_type,
                ip_address=token.ip_address,
                location=location,
                last_active=token.created_at,
                is_current=(token.jti == current_jti)
            ))
        
        return sessions

    @staticmethod
    async def revoke_session(
        db: AsyncSession,
        user_id: int,
        jti: str,
        current_jti: str
    ) -> bool:
        """Revoca una sesión específica"""
        # No permitir revocar la sesión actual
        if jti == current_jti:
            return False
        
        result = await db.execute(
            select(RefreshToken)
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.jti == jti,
                    RefreshToken.revoked_at.is_(None)
                )
            )
        )
        
        token = result.scalar_one_or_none()
        if not token:
            return False
        
        token.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    @staticmethod
    async def revoke_all_sessions(
        db: AsyncSession,
        user_id: int,
        current_jti: str
    ) -> int:
        """Revoca todas las sesiones excepto la actual"""
        now = datetime.now(timezone.utc)
        
        result = await db.execute(
            select(RefreshToken)
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.jti != current_jti,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now
                )
            )
        )
        
        tokens = result.scalars().all()
        count = 0
        
        for token in tokens:
            token.revoked_at = now
            count += 1
        
        await db.commit()
        return count
