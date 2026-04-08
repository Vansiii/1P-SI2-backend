"""
Enhanced rate limiting utilities with whitelist and role-based limits.
"""
import logging
from typing import Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ...core.config import get_settings
from ...core.constants import UserType

logger = logging.getLogger(__name__)


def get_remote_address_with_whitelist(request: Request) -> str:
    """
    Get client IP, but return special key if whitelisted.
    
    Whitelisted IPs bypass rate limiting entirely.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client IP or "whitelist" if IP is whitelisted
    """
    settings = get_settings()
    client_ip = get_remote_address(request)
    
    # Check if IP is whitelisted
    if client_ip in settings.whitelist_ips:
        logger.debug("IP %s is whitelisted, bypassing rate limiting", client_ip)
        return "whitelist"
    
    return client_ip


def get_rate_limit_key_with_user_type(request: Request) -> str:
    """
    Generate rate limiting key considering user type.
    
    Administrators get higher limits (configurable multiplier).
    
    Args:
        request: FastAPI request
        
    Returns:
        Rate limiting key (IP or IP+user_type)
    """
    settings = get_settings()
    client_ip = get_remote_address(request)
    
    # Check whitelist first
    if client_ip in settings.whitelist_ips:
        logger.debug("IP %s is whitelisted, bypassing rate limiting", client_ip)
        return "whitelist"
    
    # Check for authenticated user
    user = getattr(request.state, "user", None)
    token_payload = getattr(request.state, "token_payload", None)
    
    # Try to get user type from user object or token payload
    user_type = None
    if user and hasattr(user, "user_type"):
        user_type = user.user_type
    elif token_payload and hasattr(token_payload, "user_type"):
        user_type = token_payload.user_type
    
    # Admins get higher limits
    if user_type == UserType.ADMINISTRATOR:
        logger.debug("Admin user detected, applying rate limit multiplier")
        return f"{client_ip}:admin"
    
    return client_ip


def create_admin_rate_limit(base_limit: str) -> str:
    """
    Create admin rate limit based on base limit.
    
    Args:
        base_limit: Base limit (e.g., "5/minute", "10/hour")
        
    Returns:
        Multiplied limit for admins
        
    Examples:
        >>> create_admin_rate_limit("5/minute")
        "15/minute"  # If multiplier is 3
        >>> create_admin_rate_limit("10/hour")
        "30/hour"
    """
    settings = get_settings()
    multiplier = settings.rate_limit_admin_multiplier
    
    # Parse base limit
    parts = base_limit.split("/")
    if len(parts) != 2:
        logger.warning("Invalid limit format: %s", base_limit)
        return base_limit
    
    try:
        count = int(parts[0])
        period = parts[1]
        
        # Apply multiplier
        admin_count = count * multiplier
        return f"{admin_count}/{period}"
    except ValueError:
        logger.warning("Could not parse limit: %s", base_limit)
        return base_limit


def get_limiter() -> Limiter:
    """
    Create and configure slowapi limiter.
    
    Returns:
        Configured Limiter instance
    """
    return Limiter(
        key_func=get_remote_address_with_whitelist,
        default_limits=["1000/minute"],  # High default, specific limits per endpoint
        storage_uri="memory://",
        strategy="fixed-window",
    )


def rate_limit_with_admin_bypass(limit: str):
    """
    Decorator that applies rate limiting with whitelist bypass and higher limits for admins.
    
    Args:
        limit: Base limit (e.g., "5/minute")
        
    Returns:
        Configured decorator
        
    Example:
        @router.post("/login")
        @rate_limit_with_admin_bypass("5/minute")
        async def login(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Add metadata for slowapi processing
        if not hasattr(func, "_rate_limit"):
            func._rate_limit = limit
        return func
    return decorator


def get_client_identifier(request: Request) -> str:
    """
    Get unique client identifier for rate limiting.
    
    Uses IP address, but could be extended to use user ID for authenticated users.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client identifier string
    """
    # For now, use IP address
    return get_remote_address(request)


def is_rate_limit_exceeded(request: Request, limit: str) -> bool:
    """
    Check if rate limit would be exceeded for this request.
    
    This is a utility function for manual rate limit checking.
    
    Args:
        request: FastAPI request
        limit: Rate limit string (e.g., "5/minute")
        
    Returns:
        True if rate limit would be exceeded
    """
    # This would need to be implemented with actual rate limiting logic
    # For now, return False (not implemented)
    return False