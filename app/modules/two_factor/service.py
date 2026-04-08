"""
Service for two-factor authentication operations.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    InvalidCredentialsException,
    RateLimitException,
    TokenExpiredException,
    UserNotFoundException,
    ValidationException,
    generate_otp,
    get_logger,
    get_settings,
    hash_otp,
    verify_otp,
    verify_password,
)
from ...models.two_factor_auth import TwoFactorAuth
from ...models.user import User
from ...modules.audit.service import AuditAction, AuditService, ResourceType
from ...modules.auth.repository import UserRepository
from ...modules.notifications.service import EmailService
from .repository import TwoFactorRepository

logger = get_logger(__name__)
MAX_OTP_ATTEMPTS = 3


class TwoFactorService:
    """Service for two-factor authentication operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.two_factor_repo = TwoFactorRepository(session)
        self.user_repo = UserRepository(session)
        self.audit_service = AuditService(session)
        self.email_service = EmailService()
        self.settings = get_settings()
    
    async def enable_2fa(self, email: str) -> dict:
        """
        Start the 2FA activation process.
        Generate OTP code and send via email.
        
        Args:
            email: User email
            
        Returns:
            Success message with email confirmation
            
        Raises:
            UserNotFoundException: If user doesn't exist
            ValidationException: If 2FA already enabled
        """
        # Find user by email
        user = await self.user_repo.find_active_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        if user.two_factor_enabled:
            raise ValidationException("2FA ya está habilitado para este usuario")
        
        # Generate OTP code
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.otp_expire_minutes)
        
        # Find or create 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        
        if two_factor:
            # Update existing record
            await self.two_factor_repo.update(two_factor.id, {
                "otp_code_hash": otp_hash,
                "otp_expires_at": expires_at,
                "is_enabled": False,
                "otp_attempts": 0,
            })
        else:
            # Create new record
            two_factor = TwoFactorAuth(
                user_id=user.id,
                otp_code_hash=otp_hash,
                otp_expires_at=expires_at,
                is_enabled=False,
                otp_attempts=0,
            )
            self.session.add(two_factor)
            await self.session.commit()
        
        # Send email with OTP code
        try:
            user_name = getattr(user, 'first_name', user.email)
            await self._send_otp_email(user.email, user_name, otp_code)
            logger.info("2FA activation OTP sent", user_id=user.id, email=email)
        except Exception as e:
            logger.error("Error sending 2FA OTP email", user_id=user.id, error=str(e))
        
        return {
            "message": "Código de verificación enviado por email",
            "email": user.email,
        }
    
    async def generate_login_otp(self, email: str) -> dict:
        """
        Generate and send OTP code for login authentication.
        
        Args:
            email: User email
            
        Returns:
            Success message with email confirmation
            
        Raises:
            UserNotFoundException: If user doesn't exist
            ValidationException: If 2FA not enabled
        """
        # Find user by email
        user = await self.user_repo.find_active_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        if not user.two_factor_enabled:
            raise ValidationException("2FA no está habilitado para este usuario")
        
        # Generate OTP code
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.otp_expire_minutes)
        
        # Find or create 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        
        if two_factor:
            # Update existing record
            await self.two_factor_repo.update(two_factor.id, {
                "otp_code_hash": otp_hash,
                "otp_expires_at": expires_at,
                "otp_attempts": 0,
            })
        else:
            # Create new record (shouldn't happen if 2FA is enabled, but handle it)
            two_factor = TwoFactorAuth(
                user_id=user.id,
                otp_code_hash=otp_hash,
                otp_expires_at=expires_at,
                is_enabled=True,
                otp_attempts=0,
            )
            self.session.add(two_factor)
            await self.session.commit()
        
        # Send email with OTP code
        try:
            user_name = getattr(user, 'first_name', user.email)
            await self._send_otp_email(user.email, user_name, otp_code, is_login=True)
            logger.info("Login 2FA OTP sent", user_id=user.id, email=email)
        except Exception as e:
            logger.error("Error sending login 2FA OTP email", user_id=user.id, error=str(e))
        
        return {
            "message": "Código de verificación enviado por email",
            "email": user.email,
        }
    
    async def verify_otp_code(self, email: str, otp: str) -> dict:
        """
        Verify OTP code and activate 2FA if correct.
        
        Args:
            email: User email
            otp: OTP code to verify
            
        Returns:
            Success message with 2FA status
            
        Raises:
            UserNotFoundException: If user doesn't exist
            ValidationException: If no pending 2FA request or already enabled
            TokenExpiredException: If OTP expired
            RateLimitException: If too many attempts
            InvalidCredentialsException: If OTP is incorrect
        """
        # Find user
        user = await self.user_repo.find_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        # Find 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        if not two_factor:
            raise ValidationException("No hay solicitud de 2FA pendiente")
        
        # Check if already enabled
        if two_factor.is_enabled:
            raise ValidationException("2FA ya está activado")
        
        # Check expiration
        if not two_factor.otp_expires_at or datetime.now(UTC) > two_factor.otp_expires_at:
            raise TokenExpiredException("El código ha expirado. Solicita uno nuevo")
        
        # Check attempts
        if two_factor.otp_attempts >= MAX_OTP_ATTEMPTS:
            raise RateLimitException("Demasiados intentos fallidos. Solicita un nuevo código")
        
        # Verify OTP code
        if not two_factor.otp_code_hash or not verify_otp(otp, two_factor.otp_code_hash):
            updated_record = await self.two_factor_repo.increment_attempts(two_factor.id)
            remaining = max(0, MAX_OTP_ATTEMPTS - updated_record.otp_attempts)
            logger.warning("Invalid 2FA OTP attempt", user_id=user.id, attempts=updated_record.otp_attempts)

            if remaining == 0:
                await self.two_factor_repo.update(two_factor.id, {
                    "otp_code_hash": None,
                    "otp_expires_at": None,
                })
                raise RateLimitException("Has agotado los intentos. El código fue bloqueado, solicita uno nuevo")

            raise InvalidCredentialsException(f"Código incorrecto. Te quedan {remaining} intentos")
        
        # Code correct - activate 2FA
        await self.two_factor_repo.update(two_factor.id, {"is_enabled": True})
        await self.user_repo.update(user.id, {"two_factor_enabled": True})
        
        # Log audit action
        await self.audit_service.log_action(
            action=AuditAction.TWO_FA_ENABLED,
            user_id=user.id,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            ip_address="unknown",
            details={"email": user.email},
        )
        
        logger.info("2FA enabled successfully", user_id=user.id, email=email)
        
        return {
            "message": "2FA activado exitosamente",
            "two_factor_enabled": True,
        }
    
    async def verify_login_otp(self, email: str, otp: str) -> dict:
        """
        Verify OTP code for login authentication.
        
        Args:
            email: User email
            otp: OTP code to verify
            
        Returns:
            Success message
            
        Raises:
            UserNotFoundException: If user doesn't exist
            ValidationException: If 2FA not enabled or no pending request
            TokenExpiredException: If OTP expired
            RateLimitException: If too many attempts
            InvalidCredentialsException: If OTP is incorrect
        """
        # Find user
        user = await self.user_repo.find_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        if not user.two_factor_enabled:
            raise ValidationException("2FA no está habilitado para este usuario")
        
        # Find 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        if not two_factor:
            raise ValidationException("No hay solicitud de 2FA pendiente")
        
        # Check expiration
        if not two_factor.otp_expires_at or datetime.now(UTC) > two_factor.otp_expires_at:
            raise TokenExpiredException("El código ha expirado. Solicita uno nuevo")
        
        # Check attempts
        if two_factor.otp_attempts >= MAX_OTP_ATTEMPTS:
            raise RateLimitException("Demasiados intentos fallidos. Solicita un nuevo código")
        
        # Verify OTP code
        if not two_factor.otp_code_hash or not verify_otp(otp, two_factor.otp_code_hash):
            updated_record = await self.two_factor_repo.increment_attempts(two_factor.id)
            remaining = max(0, MAX_OTP_ATTEMPTS - updated_record.otp_attempts)
            logger.warning("Invalid login 2FA OTP attempt", user_id=user.id, attempts=updated_record.otp_attempts)

            if remaining == 0:
                await self.two_factor_repo.update(two_factor.id, {
                    "otp_code_hash": None,
                    "otp_expires_at": None,
                })
                raise RateLimitException("Has agotado los intentos. El código fue bloqueado, solicita uno nuevo")

            raise InvalidCredentialsException(f"Código incorrecto. Te quedan {remaining} intentos")
        
        # Code correct - clear OTP for security
        await self.two_factor_repo.update(two_factor.id, {
            "otp_code_hash": None,
            "otp_expires_at": None,
            "otp_attempts": 0,
        })
        
        logger.info("Login 2FA verified successfully", user_id=user.id, email=email)
        
        return {
            "message": "Código verificado exitosamente",
        }
    
    async def disable_2fa(self, user: User, password: str) -> dict:
        """
        Disable 2FA for a user.
        Requires current password for confirmation.
        
        Args:
            user: User object
            password: Current password for verification
            
        Returns:
            Success message with 2FA status
            
        Raises:
            InvalidCredentialsException: If password is incorrect
            ValidationException: If 2FA not enabled
        """
        # Verify password
        if not verify_password(password, user.password_hash):
            logger.warning("Invalid password in 2FA disable attempt", user_id=user.id)
            raise InvalidCredentialsException("Contraseña incorrecta")
        
        if not user.two_factor_enabled:
            raise ValidationException("2FA no está habilitado")
        
        # Disable 2FA
        await self.user_repo.update(user.id, {"two_factor_enabled": False})
        
        # Delete 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        if two_factor:
            await self.two_factor_repo.delete(two_factor.id)
        
        # Log audit action
        await self.audit_service.log_action(
            action=AuditAction.TWO_FA_DISABLED,
            user_id=user.id,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            ip_address="unknown",
            details={"email": user.email},
        )
        
        # Send notification email
        try:
            user_name = getattr(user, 'first_name', user.email)
            await self._send_2fa_disabled_email(user.email, user_name)
            logger.info("2FA disabled notification sent", user_id=user.id)
        except Exception as e:
            logger.error("Error sending 2FA disabled notification", user_id=user.id, error=str(e))
        
        logger.info("2FA disabled successfully", user_id=user.id)
        
        return {
            "message": "2FA desactivado exitosamente",
            "two_factor_enabled": False,
        }
    
    async def resend_otp(self, email: str) -> dict:
        """
        Resend OTP code.
        Limited to 1 resend per minute.
        
        Args:
            email: User email
            
        Returns:
            Success message with email confirmation
            
        Raises:
            UserNotFoundException: If user doesn't exist
            ValidationException: If no pending 2FA request
            RateLimitException: If resend too soon
        """
        # Find user
        user = await self.user_repo.find_by_email(email)
        if not user:
            raise UserNotFoundException(f"Usuario con email {email}")
        
        # Find 2FA record
        two_factor = await self.two_factor_repo.find_by_user_id(user.id)
        if not two_factor:
            raise ValidationException("No hay solicitud de 2FA pendiente")
        
        # Check rate limit (1 minute) based on the current OTP issuance time.
        # If current OTP is blocked/cleared (no expiration), allow immediate resend.
        if two_factor.otp_expires_at:
            issued_at = two_factor.otp_expires_at - timedelta(minutes=self.settings.otp_expire_minutes)
            if datetime.now(UTC) < issued_at + timedelta(minutes=1):
                raise RateLimitException("Debes esperar 1 minuto antes de solicitar un nuevo código")
        
        # Generate new code
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.otp_expire_minutes)
        
        # Update record
        await self.two_factor_repo.update(two_factor.id, {
            "otp_code_hash": otp_hash,
            "otp_expires_at": expires_at,
            "otp_attempts": 0,
        })
        
        # Send email
        try:
            user_name = getattr(user, 'first_name', user.email)
            await self._send_otp_email(user.email, user_name, otp_code, is_resend=True)
            logger.info("2FA OTP resent", user_id=user.id, email=email)
        except Exception as e:
            logger.error("Error resending 2FA OTP email", user_id=user.id, error=str(e))
        
        return {
            "message": "Nuevo código enviado por email",
            "email": user.email,
        }
    
    async def _send_otp_email(self, email: str, user_name: str, otp_code: str, is_resend: bool = False, is_login: bool = False) -> None:
        """Send OTP code via email."""
        await self.email_service.send_otp_email(email, user_name, otp_code)
    
    async def _send_2fa_disabled_email(self, email: str, user_name: str) -> None:
        """Send 2FA disabled notification email."""
        await self.email_service.send_security_notification_email(
            to_email=email,
            user_name=user_name,
            event_type="2FA Desactivado",
            details="La autenticación de dos factores ha sido desactivada en tu cuenta. Si no realizaste esta acción, contacta con soporte inmediatamente."
        )