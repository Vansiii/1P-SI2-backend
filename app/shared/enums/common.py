"""
Common enums for the application.
"""
from enum import Enum


class UserType(str, Enum):
    """User type enumeration."""
    
    CLIENT = "client"
    WORKSHOP = "workshop"
    TECHNICIAN = "technician"
    ADMINISTRATOR = "administrator"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class UserStatus(str, Enum):
    """User status enumeration."""
    
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class EmailProvider(str, Enum):
    """Email provider enumeration."""
    
    SMTP = "smtp"
    API = "api"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class Environment(str, Enum):
    """Environment enumeration."""
    
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class LogLevel(str, Enum):
    """Log level enumeration."""
    
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class ServiceStatus(str, Enum):
    """Service status enumeration."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class IncidentStatus(str, Enum):
    """Incident status enumeration."""
    
    REPORTED = "reported"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class EvidenceType(str, Enum):
    """Evidence type enumeration."""
    
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]


class NotificationType(str, Enum):
    """Notification type enumeration."""
    
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    
    @classmethod
    def values(cls) -> list[str]:
        """Get all enum values."""
        return [item.value for item in cls]