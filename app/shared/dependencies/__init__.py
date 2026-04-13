"""
Shared dependencies module.
"""

from .auth import (
    get_current_admin,
    get_current_client,
    get_current_technician,
    get_current_token_payload,
    get_current_user,
    get_current_workshop_user,
)
from .common import get_pagination_params
from .database import get_async_session

__all__ = [
    "get_current_token_payload",
    "get_current_user",
    "get_current_client",
    "get_current_workshop_user",
    "get_current_technician",
    "get_current_admin",
    "get_pagination_params",
    "get_async_session",
]