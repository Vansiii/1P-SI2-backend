"""
Notifications module for email and other notification services.
"""

from .providers import EmailProvider, get_email_provider
from .service import NotificationService

__all__ = [
    "EmailProvider",
    "get_email_provider",
    "NotificationService",
]