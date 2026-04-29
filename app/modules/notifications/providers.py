"""
Email providers for notification services.
"""
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from ...core import get_logger, get_settings

logger = get_logger(__name__)


class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Send an email."""
        pass


class BrevoSMTPProvider(EmailProvider):
    """Brevo SMTP email provider."""
    
    def __init__(self):
        self.settings = get_settings()
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Send email via Brevo SMTP."""
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email or self.settings.smtp_from_email
            msg["To"] = to_email
            
            # Add text content if provided
            if text_content:
                text_part = MIMEText(text_content, "plain", "utf-8")
                msg.attach(text_part)
            
            # Add HTML content
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.settings.smtp_server, self.settings.smtp_port) as server:
                server.starttls()
                server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(msg)
            
            logger.info("Email sent via SMTP", to_email=to_email, subject=subject)
            return True
            
        except Exception as e:
            logger.error("Failed to send email via SMTP", to_email=to_email, error=str(e))
            return False


class BrevoAPIProvider(EmailProvider):
    """Brevo API email provider."""
    
    def __init__(self):
        self.settings = get_settings()
        self.api_url = "https://api.brevo.com/v3/smtp/email"
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Send email via Brevo API."""
        try:
            headers = {
                "accept": "application/json",
                "api-key": self.settings.brevo_api_key,
                "content-type": "application/json",
            }
            
            payload = {
                "sender": {
                    "name": from_name or self.settings.smtp_from_name,
                    "email": from_email or self.settings.smtp_from_email,
                },
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content,
            }
            
            if text_content:
                payload["textContent"] = text_content
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
            
            logger.info("Email sent via API", to_email=to_email, subject=subject)
            return True
            
        except Exception as e:
            logger.error("Failed to send email via API", to_email=to_email, error=str(e))
            return False


class ConsoleEmailProvider(EmailProvider):
    """Console email provider for development/testing."""
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """Print email to console instead of sending."""
        logger.info(f"📧 EMAIL TO: {to_email} | SUBJECT: {subject}")
        logger.debug(f"FROM: {from_name or 'Sistema'} <{from_email or 'noreply@example.com'}>")
        if text_content:
            logger.debug(f"TEXT CONTENT: {text_content[:200]}...")
        logger.debug(f"HTML CONTENT: {html_content[:200]}...")
        
        logger.info("Email printed to console", to_email=to_email, subject=subject)
        return True


def get_email_provider() -> EmailProvider:
    """Get the configured email provider."""
    settings = get_settings()
    
    # En desarrollo, usar console provider
    if settings.environment == "development":
        logger.info("Using console email provider (development mode)")
        return ConsoleEmailProvider()
    
    # Seleccionar provider basado en EMAIL_PROVIDER
    if settings.email_provider == "api":
        if settings.brevo_api_key:
            logger.info("Using Brevo API email provider")
            return BrevoAPIProvider()
        else:
            logger.warning("API provider selected but BREVO_API_KEY not configured, falling back to console")
            return ConsoleEmailProvider()
    
    elif settings.email_provider == "smtp":
        if settings.brevo_smtp_host and settings.brevo_smtp_user and settings.brevo_smtp_password:
            logger.info("Using Brevo SMTP email provider")
            return BrevoSMTPProvider()
        else:
            logger.warning("SMTP provider selected but credentials not configured, falling back to console")
            return ConsoleEmailProvider()
    
    else:
        logger.warning("No valid email provider configured, using console provider")
        return ConsoleEmailProvider()