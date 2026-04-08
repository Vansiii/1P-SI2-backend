"""Templates de email para el sistema."""

from .account_unlocked_email import (
    get_account_unlocked_email_html,
    get_account_unlocked_email_text,
)
from .otp_email import get_otp_email_html, get_otp_email_text
from .password_changed_email import (
    get_password_changed_email_html,
    get_password_changed_email_text,
)
from .password_reset_email import (
    get_password_reset_email_html,
    get_password_reset_email_text,
)
from .password_reset_otp_email import (
    get_password_reset_otp_email_html,
    get_password_reset_otp_email_text,
)
from .security_notification_email import (
    get_security_notification_email_html,
    get_security_notification_email_text,
)
from .welcome_email import get_welcome_email_html, get_welcome_email_text

__all__ = [
    "get_welcome_email_html",
    "get_welcome_email_text",
    "get_password_reset_email_html",
    "get_password_reset_email_text",
    "get_password_reset_otp_email_html",
    "get_password_reset_otp_email_text",
    "get_otp_email_html",
    "get_otp_email_text",
    "get_password_changed_email_html",
    "get_password_changed_email_text",
    "get_account_unlocked_email_html",
    "get_account_unlocked_email_text",
    "get_security_notification_email_html",
    "get_security_notification_email_text",
]
