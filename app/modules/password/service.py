"""
Service for password management operations.
"""
import hashlib
import secrets
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    InvalidCredentialsException,
    InvalidTokenException,
    TokenExpiredException,
    UserNotFoundException,
    ValidationException,
    WeakPasswordException,
    get_logger,
    get_settings,
    hash_password,
    validate_password_strength,
    verify_password,
)
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.password_reset_token import PasswordResetToken
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from ...modules.audit.service import AuditService, AuditAction, ResourceType
from ...modules.auth.repository import UserRepository
from ...modules.tokens.service import TokenService
from ...modules.notifications.service import EmailService
from .repository import PasswordResetRepository

logger = get_logger(__name__)


class PasswordService:
    """Service for password management operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.password_repo = PasswordResetRepository(session)
        self.user_repo = UserRepository(session)
        self.token_service = TokenService(session)
        self.audit_service = AuditService(session)
        self.email_service = EmailService()
        self.settings = get_settings()
    
    async def forgot_password(self, email: str) -> str:
        """
        Generate recovery token and send email.
        
        Args:
            email: User email
            
        Returns:
            Success message (same regardless of email existence for security)
        """
        success_message = (
            "Si el correo existe en nuestro sistema, "
            "recibirás un email con instrucciones para recuperar tu contraseña"
        )
        
        # Find user by email
        user = await self.user_repo.find_by_email(email)
        
        if not user:
            logger.info("Password reset requested for non-existent email", email=email)
            return success_message
        
        # Check for recent requests (last 5 minutes)
        recent_cutoff = datetime.now(UTC) - timedelta(minutes=5)
        recent_token = await self.password_repo.find_recent_unused_token(
            user.id, recent_cutoff
        )
        
        if recent_token:
            logger.info("Recent password reset request ignored", user_id=user.id)
            return (
                "Ya se ha enviado un correo de recuperación recientemente. "
                "Por favor, revisa tu bandeja de entrada o espera 5 minutos antes de solicitar otro."
            )
        
        # Generate unique token
        reset_token = secrets.token_urlsafe(32)
        reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        
        # Save token in database
        password_reset = PasswordResetToken(
            user_id=user.id,
            token_hash=reset_token_hash,
            expires_at=expires_at,
            used=False,
        )
        
        self.session.add(password_reset)
        await self.session.commit()
        
        # Send email
        try:
            user_name = await self._get_user_display_name(user)
            await self.email_service.send_password_reset_email(
                to_email=user.email,
                user_name=user_name,
                reset_token=reset_token,
            )
            logger.info("Password reset email sent", user_id=user.id, email=email)
        except Exception as e:
            logger.error("Error sending password reset email", user_id=user.id, error=str(e))
        
        return success_message
    
    async def forgot_password_mobile(self, email: str) -> str:
        """
        Generate OTP code for mobile password recovery.
        
        Args:
            email: User email
            
        Returns:
            Success message (same regardless of email existence for security)
        """
        success_message = (
            "Si el correo existe en nuestro sistema, "
            "recibirás un código de verificación para recuperar tu contraseña"
        )
        
        # Find user by email
        user = await self.user_repo.find_by_email(email)
        
        if not user:
            logger.info("Mobile password reset requested for non-existent email", email=email)
            return success_message
        
        # Check for recent requests (last 2 minutes)
        recent_cutoff = datetime.now(UTC) - timedelta(minutes=2)
        recent_token = await self.password_repo.find_recent_unused_token(
            user.id, recent_cutoff
        )
        
        if recent_token:
            logger.info("Recent mobile password reset request ignored", user_id=user.id)
            return (
                "Ya se ha enviado un código de recuperación recientemente. "
                "Por favor, revisa tu correo o espera 2 minutos antes de solicitar otro."
            )
        
        # Generate 6-digit OTP code
        otp_code = f"{random.randint(100000, 999999)}"
        otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        
        # Save OTP in database (reusing PasswordResetToken model)
        password_reset = PasswordResetToken(
            user_id=user.id,
            token_hash=otp_hash,
            expires_at=expires_at,
            used=False,
        )
        
        self.session.add(password_reset)
        await self.session.commit()
        
        # Send email with OTP
        try:
            user_name = await self._get_user_display_name(user)
            await self.email_service.send_password_reset_otp_email(
                to_email=user.email,
                user_name=user_name,
                otp_code=otp_code,
            )
            logger.info("Password reset OTP email sent", user_id=user.id, email=email)
        except Exception as e:
            logger.error("Error sending password reset OTP email", user_id=user.id, error=str(e))
        
        return success_message
    
    async def verify_password_otp(self, email: str, otp_code: str) -> str:
        """
        Verify OTP code and generate reset token for mobile.
        
        Args:
            email: User email
            otp_code: 6-digit OTP code
            
        Returns:
            Reset token to use for password reset
            
        Raises:
            UserNotFoundException: If user doesn't exist
            InvalidTokenException: If OTP is invalid or used
            TokenExpiredException: If OTP is expired
        """
        # Find user
        user = await self.user_repo.find_by_email(email)
        if not user:
            logger.warning("OTP verification for non-existent email", email=email)
            raise UserNotFoundException("Usuario no encontrado")
        
        # Find OTP token
        otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        password_reset = await self.password_repo.find_by_token_hash(otp_hash)
        
        if not password_reset or password_reset.user_id != user.id:
            logger.warning("Invalid OTP code used", email=email)
            raise InvalidTokenException("Código de verificación inválido")
        
        # Check if expired
        if password_reset.expires_at < datetime.now(UTC):
            logger.warning("Expired OTP code used", email=email)
            raise TokenExpiredException("El código de verificación ha expirado. Solicita uno nuevo")
        
        # Check if already used
        if password_reset.used or password_reset.used_at is not None:
            logger.warning("Used OTP code attempted", email=email)
            raise InvalidTokenException("Este código ya fue utilizado. Solicita uno nuevo")
        
        # Mark OTP as used
        password_reset.used = True
        password_reset.used_at = datetime.now(UTC)
        
        # Generate new reset token (valid for 15 minutes)
        reset_token = secrets.token_urlsafe(32)
        reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        
        # Save reset token
        new_reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=reset_token_hash,
            expires_at=expires_at,
            used=False,
        )
        
        self.session.add(new_reset_token)
        await self.session.commit()
        
        logger.info("OTP verified successfully, reset token generated", user_id=user.id)
        return reset_token
    
    async def reset_password(self, token: str, new_password: str) -> str:
        """
        Reset password using recovery token.
        
        Args:
            token: Recovery token
            new_password: New password
            
        Returns:
            Success message
            
        Raises:
            WeakPasswordException: If password is weak
            InvalidTokenException: If token is invalid or used
            TokenExpiredException: If token is expired
            UserNotFoundException: If user doesn't exist
        """
        # Validate password strength
        is_valid, error_message = validate_password_strength(new_password)
        if not is_valid:
            raise WeakPasswordException(error_message)
        
        # Find token
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        password_reset = await self.password_repo.find_by_token_hash(token_hash)
        
        if not password_reset:
            logger.warning("Invalid password reset token used")
            raise InvalidTokenException("Token de recuperación inválido")
        
        # Check if expired
        if password_reset.expires_at < datetime.now(UTC):
            logger.warning("Expired password reset token used", token_id=password_reset.id)
            raise TokenExpiredException("El token de recuperación ha expirado. Solicita uno nuevo")
        
        # Check if already used
        if password_reset.used or password_reset.used_at is not None:
            logger.warning("Used password reset token attempted", token_id=password_reset.id)
            raise InvalidTokenException("Este token ya fue utilizado. Solicita uno nuevo")
        
        # Get user
        user = await self.user_repo.find_by_id(password_reset.user_id)
        if not user:
            logger.error("User not found for valid token", user_id=password_reset.user_id)
            raise UserNotFoundException(f"Usuario {password_reset.user_id}")
        
        # Update password
        user.password_hash = hash_password(new_password)
        
        # Mark token as used
        password_reset.used = True
        password_reset.used_at = datetime.now(UTC)
        
        await self.session.commit()
        
        # Log audit action
        await self.audit_service.log_action(
            action=AuditAction.PASSWORD_RESET,
            user_id=user.id,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            ip_address="unknown",
            details={"email": user.email},
        )
        
        # Revoke all active sessions
        await self.token_service.revoke_all_user_tokens(user.id)
        
        # Send confirmation email
        try:
            user_name = await self._get_user_display_name(user)
            await self.email_service.send_password_changed_email(
                to_email=user.email,
                user_name=user_name,
            )
            logger.info("Password reset confirmation email sent", user_id=user.id)
        except Exception as e:
            logger.error("Error sending password reset confirmation", user_id=user.id, error=str(e))
        
        logger.info("Password reset successfully", user_id=user.id)
        return "Contraseña actualizada exitosamente. Inicia sesión con tu nueva contraseña"
    
    async def change_password(
        self, 
        user_id: int, 
        current_password: str, 
        new_password: str
    ) -> str:
        """
        Change password from authenticated profile.
        
        Args:
            user_id: Authenticated user ID
            current_password: Current password
            new_password: New password
            
        Returns:
            Success message
            
        Raises:
            WeakPasswordException: If new password is weak
            UserNotFoundException: If user doesn't exist
            InvalidCredentialsException: If current password is incorrect
            ValidationException: If new password is same as current
        """
        # Validate new password strength
        is_valid, error_message = validate_password_strength(new_password)
        if not is_valid:
            raise WeakPasswordException(error_message)
        
        # Get user
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"Usuario {user_id}")
        
        # Verify current password
        if not verify_password(current_password, user.password_hash):
            logger.warning("Invalid current password in change request", user_id=user_id)
            raise InvalidCredentialsException("La contraseña actual es incorrecta")
        
        # Verify new password is different
        if verify_password(new_password, user.password_hash):
            raise ValidationException("La nueva contraseña debe ser diferente a la actual")
        
        # Update password
        user.password_hash = hash_password(new_password)
        await self.session.commit()
        
        # Log audit action
        await self.audit_service.log_action(
            action=AuditAction.PASSWORD_CHANGE,
            user_id=user.id,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            ip_address="unknown",
            details={"email": user.email},
        )
        
        # Revoke all sessions for security
        await self.token_service.revoke_all_user_tokens(user.id)
        
        # Send notification email
        try:
            user_name = await self._get_user_display_name(user)
            await self.email_service.send_password_changed_email(
                to_email=user.email,
                user_name=user_name,
            )
            logger.info("Password change notification email sent", user_id=user.id)
        except Exception as e:
            logger.error("Error sending password change notification", user_id=user.id, error=str(e))
        
        logger.info("Password changed successfully", user_id=user.id)
        return "Contraseña actualizada exitosamente. Deberás iniciar sesión nuevamente"
    
    async def _get_user_display_name(self, user: User) -> str:
        """Get display name for user based on type."""
        try:
            if user.user_type == "client":
                client = await self.session.get(Client, user.id)
                return getattr(client, 'full_name', user.email)
            elif user.user_type == "workshop":
                workshop = await self.session.get(Workshop, user.id)
                return getattr(workshop, 'workshop_name', user.email)
            elif user.user_type == "technician":
                technician = await self.session.get(Technician, user.id)
                return getattr(technician, 'full_name', user.email)
            elif user.user_type == "admin":
                admin = await self.session.get(Administrator, user.id)
                return getattr(admin, 'full_name', user.email)
        except Exception:
            pass
        
        return user.email