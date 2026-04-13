"""
Core logging configuration with structured logging support.
"""
import logging
import logging.config
import sys
from typing import Any

import structlog

from .config import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        stream=sys.stdout,
        format="%(message)s",
    )
    
    # Configure structlog processors based on environment
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if settings.log_format == "json":
        # JSON format for production
        processors.extend([
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Human-readable format for development
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class RequestContextFilter(logging.Filter):
    """Add request context to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add request context to log record if available."""
        # This will be populated by middleware
        record.request_id = getattr(record, 'request_id', None)
        record.user_id = getattr(record, 'user_id', None)
        record.ip_address = getattr(record, 'ip_address', None)
        return True


def setup_request_logging() -> None:
    """Setup request-specific logging configuration."""
    # Add request context filter to all handlers
    for handler in logging.root.handlers:
        handler.addFilter(RequestContextFilter())


# Logging utilities
def log_security_event(
    event_type: str,
    user_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log security-related events."""
    logger = get_logger("security")
    logger.warning(
        "Security event",
        event_type=event_type,
        user_id=user_id,
        ip_address=ip_address,
        details=details or {},
    )


def log_business_event(
    event_type: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log business-related events."""
    logger = get_logger("business")
    logger.info(
        "Business event",
        event_type=event_type,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )


def log_performance_metric(
    metric_name: str,
    value: float,
    unit: str = "ms",
    tags: dict[str, str] | None = None,
) -> None:
    """Log performance metrics."""
    logger = get_logger("performance")
    logger.info(
        "Performance metric",
        metric_name=metric_name,
        value=value,
        unit=unit,
        tags=tags or {},
    )