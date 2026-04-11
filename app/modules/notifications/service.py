"""
Service for notification operations.
"""
from typing import Optional

from ...core import get_logger, get_settings
from ...templates.account_unlocked_email import get_account_unlocked_email_html, get_account_unlocked_email_text
from ...templates.otp_email import get_otp_email_html, get_otp_email_text
from ...templates.password_changed_email import get_password_changed_email_html, get_password_changed_email_text
from ...templates.password_reset_email import get_password_reset_email_html, get_password_reset_email_text
from ...templates.password_reset_otp_email import get_password_reset_otp_email_html, get_password_reset_otp_email_text
from ...templates.security_notification_email import get_security_notification_email_html, get_security_notification_email_text
from ...templates.welcome_email import get_welcome_email_html, get_welcome_email_text
from .providers import EmailProvider, get_email_provider

logger = get_logger(__name__)


class NotificationService:
    """Service for notification operations."""
    
    def __init__(self, email_provider: Optional[EmailProvider] = None):
        self.email_provider = email_provider or get_email_provider()
        self.settings = get_settings()
    
    async def send_welcome_email(
        self, 
        to_email: str, 
        user_name: str, 
        user_type: str
    ) -> bool:
        """Send welcome email to new user."""
        try:
            app_name = self.settings.app_name
            html_content = get_welcome_email_html(user_name, user_type, app_name)
            text_content = get_welcome_email_text(user_name, user_type, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Bienvenido a {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Welcome email sent", to_email=to_email, user_type=user_type)
            else:
                logger.error("Failed to send welcome email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending welcome email", to_email=to_email, error=str(e))
            return False
    
    async def send_password_reset_email(
        self, 
        to_email: str, 
        user_name: str, 
        reset_token: str
    ) -> bool:
        """Send password reset email."""
        try:
            app_name = self.settings.app_name
            # Construir URL completa para reset de contraseña
            reset_url = f"{self.settings.frontend_url}/auth/reset-password?token={reset_token}"
            
            html_content = get_password_reset_email_html(user_name, reset_url, app_name)
            text_content = get_password_reset_email_text(user_name, reset_url, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Solicitud de Restablecimiento de Contraseña - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Password reset email sent", to_email=to_email)
            else:
                logger.error("Failed to send password reset email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending password reset email", to_email=to_email, error=str(e))
            return False
    
    async def send_password_reset_otp_email(
        self, 
        to_email: str, 
        user_name: str, 
        otp_code: str
    ) -> bool:
        """Send password reset OTP email for mobile."""
        try:
            app_name = self.settings.app_name
            html_content = get_password_reset_otp_email_html(user_name, otp_code, app_name)
            text_content = get_password_reset_otp_email_text(user_name, otp_code, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Código de Recuperación de Contraseña - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Password reset OTP email sent", to_email=to_email)
            else:
                logger.error("Failed to send password reset OTP email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending password reset OTP email", to_email=to_email, error=str(e))
            return False
    
    async def send_otp_email(
        self, 
        to_email: str, 
        user_name: str, 
        otp_code: str
    ) -> bool:
        """Send OTP verification email."""
        try:
            app_name = self.settings.app_name
            html_content = get_otp_email_html(user_name, otp_code, app_name)
            text_content = get_otp_email_text(user_name, otp_code, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Código de Verificación de Seguridad - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("OTP email sent", to_email=to_email)
            else:
                logger.error("Failed to send OTP email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending OTP email", to_email=to_email, error=str(e))
            return False
    
    async def send_password_changed_email(
        self, 
        to_email: str, 
        user_name: str
    ) -> bool:
        """Send password changed notification email."""
        try:
            app_name = self.settings.app_name
            html_content = get_password_changed_email_html(user_name, app_name)
            text_content = get_password_changed_email_text(user_name, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Confirmación de Cambio de Contraseña - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Password changed email sent", to_email=to_email)
            else:
                logger.error("Failed to send password changed email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending password changed email", to_email=to_email, error=str(e))
            return False
    
    async def send_account_locked_email(
        self, 
        to_email: str, 
        user_name: str, 
        locked_until: str
    ) -> bool:
        """Send account locked notification email."""
        try:
            app_name = self.settings.app_name
            html_content = get_security_notification_email_html(
                user_name, 
                "Cuenta bloqueada por seguridad",
                f"Tu cuenta ha sido bloqueada temporalmente hasta {locked_until} debido a múltiples intentos de acceso fallidos.",
                app_name
            )
            text_content = get_security_notification_email_text(
                user_name, 
                "Cuenta bloqueada por seguridad",
                f"Tu cuenta ha sido bloqueada temporalmente hasta {locked_until} debido a múltiples intentos de acceso fallidos.",
                app_name
            )
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Alerta de Seguridad: Cuenta Bloqueada Temporalmente - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Account locked email sent", to_email=to_email)
            else:
                logger.error("Failed to send account locked email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending account locked email", to_email=to_email, error=str(e))
            return False
    
    async def send_account_unlocked_email(
        self, 
        to_email: str, 
        user_name: str
    ) -> bool:
        """Send account unlocked notification email."""
        try:
            app_name = self.settings.app_name
            html_content = get_account_unlocked_email_html(user_name, app_name)
            text_content = get_account_unlocked_email_text(user_name, app_name)
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Notificación: Cuenta Desbloqueada - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Account unlocked email sent", to_email=to_email)
            else:
                logger.error("Failed to send account unlocked email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending account unlocked email", to_email=to_email, error=str(e))
            return False
    
    async def send_security_notification_email(
        self, 
        to_email: str, 
        user_name: str, 
        event_type: str, 
        details: str
    ) -> bool:
        """Send security notification email."""
        try:
            app_name = self.settings.app_name
            html_content = get_security_notification_email_html(
                user_name, event_type, details, app_name
            )
            text_content = get_security_notification_email_text(
                user_name, event_type, details, app_name
            )
            
            success = await self.email_provider.send_email(
                to_email=to_email,
                subject=f"Alerta de Seguridad: {event_type} - {app_name}",
                html_content=html_content,
                text_content=text_content,
            )
            
            if success:
                logger.info("Security notification email sent", to_email=to_email, event_type=event_type)
            else:
                logger.error("Failed to send security notification email", to_email=to_email)
            
            return success
            
        except Exception as e:
            logger.error("Error sending security notification email", to_email=to_email, error=str(e))
            return False


# Backward compatibility - alias for existing EmailService
EmailService = NotificationService