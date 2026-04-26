"""
Core configuration module with environment-specific settings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and environment support."""
    
    # Application
    app_name: str = "MecánicoYa"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=True, alias="DEBUG")
    
    # Database
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_pool_size: int = Field(default=100, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")  # Recycle connections every hour
    
    # JWT and Security
    jwt_secret_key: str = Field(
        default="change-this-secret-in-production", 
        alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )
    
    # CORS
    cors_origins_raw: str = Field(
        default="http://localhost:4200,http://127.0.0.1:4200",
        alias="CORS_ORIGINS",
    )
    
    # Supabase Configuration (Backend - Service Role)
    supabase_url: str = Field(
        ...,  # Required, no default
        alias="SUPABASE_URL",
        description="Supabase project URL"
    )
    supabase_service_role_key: str = Field(
        ...,  # Required, no default
        alias="SUPABASE_SERVICE_ROLE_KEY",
        description="Supabase service role key (backend only, never expose to frontend)"
    )
    
    # Email Configuration
    email_provider: Literal["smtp", "api"] = Field(default="smtp", alias="EMAIL_PROVIDER")
    email_from_address: str = Field(
        default="noreply@1p-si2.com", alias="EMAIL_FROM_ADDRESS"
    )
    email_from_name: str = Field(default="Sistema de Emergencias Vehiculares", alias="EMAIL_FROM_NAME")
    
    # Frontend URL for email links
    frontend_url: str = Field(
        default="http://localhost:4200", alias="FRONTEND_URL"
    )
    
    # Brevo SMTP
    brevo_smtp_host: str = Field(default="smtp-relay.brevo.com", alias="BREVO_SMTP_HOST")
    brevo_smtp_port: int = Field(default=587, alias="BREVO_SMTP_PORT")
    brevo_smtp_user: str = Field(default="", alias="BREVO_SMTP_USER")
    brevo_smtp_password: str = Field(default="", alias="BREVO_SMTP_PASSWORD")
    
    # Brevo API
    brevo_api_key: str = Field(default="", alias="BREVO_API_KEY")
    
    # Security Settings
    password_reset_token_expire_minutes: int = Field(
        default=60, alias="PASSWORD_RESET_TOKEN_EXPIRE_MINUTES"
    )
    otp_expire_minutes: int = Field(default=5, alias="OTP_EXPIRE_MINUTES")
    max_login_attempts: int = Field(default=5, alias="MAX_LOGIN_ATTEMPTS")
    lockout_duration_minutes: int = Field(default=5, alias="LOCKOUT_DURATION_MINUTES")
    
    # Rate Limiting
    rate_limit_whitelist_ips_raw: str = Field(
        default="127.0.0.1,::1", alias="RATE_LIMIT_WHITELIST_IPS"
    )
    rate_limit_admin_multiplier: int = Field(
        default=3, alias="RATE_LIMIT_ADMIN_MULTIPLIER"
    )

    # Gemini AI Configuration
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_fallback_models: str = Field(
        default="gemini-flash-lite-latest,gemini-2.5-flash,gemini-2.0-flash-lite",
        alias="GEMINI_FALLBACK_MODELS",
    )
    gemini_timeout_seconds: int = Field(default=30, alias="GEMINI_TIMEOUT_SECONDS")
    gemini_max_media_bytes: int = Field(default=4_000_000, alias="GEMINI_MAX_MEDIA_BYTES")
    gemini_prompt_version: str = Field(default="v1", alias="GEMINI_PROMPT_VERSION")
    
    # AI Analysis Slow Detection
    ai_slow_threshold_seconds: int = Field(
        default=15,
        alias="AI_SLOW_THRESHOLD_SECONDS",
        description="Threshold in seconds to detect slow AI analysis and emit warning event"
    )
    
    # AI Analysis Timeout Configuration
    ai_max_processing_seconds: int = Field(
        default=60,
        alias="AI_MAX_PROCESSING_SECONDS",
        description="Maximum time in seconds for AI analysis processing before timeout"
    )
    
    ai_assignment_wait_timeout_seconds: int = Field(
        default=120,
        alias="AI_ASSIGNMENT_WAIT_TIMEOUT_SECONDS",
        description="Maximum time in seconds to wait for AI analysis before proceeding with assignment"
    )
    
    # Firebase Configuration
    # Option 1: JSON string (recommended for Railway/production)
    firebase_credentials_json: str = Field(
        default="",
        alias="FIREBASE_CREDENTIALS_JSON",
        description="Firebase service account JSON as string (for Railway/production)"
    )
    
    # Option 2: File path (for local development)
    firebase_service_account_path: str = Field(
        default="firebase-service-account.json",
        alias="FIREBASE_SERVICE_ACCOUNT_PATH",
        description="Path to Firebase service account JSON file (for local development)"
    )
    
    firebase_project_id: str = Field(
        default="",
        alias="FIREBASE_PROJECT_ID",
        description="Firebase project ID"
    )
    
    # Push Notifications
    push_notifications_enabled: bool = Field(
        default=True,
        alias="PUSH_NOTIFICATIONS_ENABLED",
        description="Enable/disable push notifications"
    )
    
    # Assignment and Reassignment Configuration
    assignment_timeout_minutes: int = Field(
        default=5,
        alias="ASSIGNMENT_TIMEOUT_MINUTES",
        description="Timeout in minutes for workshop to respond to assignment"
    )
    assignment_max_attempts: int = Field(
        default=5,
        alias="ASSIGNMENT_MAX_ATTEMPTS",
        description="Maximum number of workshops to try before escalating to admin"
    )
    assignment_retry_delay_seconds: int = Field(
        default=10,
        alias="ASSIGNMENT_RETRY_DELAY_SECONDS",
        description="Delay in seconds before retrying assignment after rejection"
    )
    assignment_timeout_high_priority: int = Field(
        default=3,
        alias="ASSIGNMENT_TIMEOUT_HIGH_PRIORITY",
        description="Timeout in minutes for high priority incidents"
    )
    assignment_timeout_medium_priority: int = Field(
        default=5,
        alias="ASSIGNMENT_TIMEOUT_MEDIUM_PRIORITY",
        description="Timeout in minutes for medium priority incidents"
    )
    assignment_timeout_low_priority: int = Field(
        default=10,
        alias="ASSIGNMENT_TIMEOUT_LOW_PRIORITY",
        description="Timeout in minutes for low priority incidents"
    )
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "text"] = Field(default="text", alias="LOG_FORMAT")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: str) -> str:
        """Validate JWT secret key strength."""
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 caracteres")
        if value == "change-this-secret-in-production":
            raise ValueError(
                "JWT_SECRET_KEY debe cambiarse del valor por defecto en producción"
            )
        return value
    
    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_token_expire_minutes(cls, value: int) -> int:
        """Validate access token expiration time."""
        if value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser mayor que 0")
        return value
    
    @field_validator("refresh_token_expire_days")
    @classmethod
    def validate_refresh_token_expire_days(cls, value: int) -> int:
        """Validate refresh token expiration time."""
        if value <= 0:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS debe ser mayor que 0")
        return value
    
    @field_validator("email_from_address")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        """Validate email format."""
        if "@" not in value:
            raise ValueError("EMAIL_FROM_ADDRESS debe tener formato de email válido")
        return value
    
    @field_validator("db_pool_size", "db_max_overflow", "db_pool_timeout", "db_pool_recycle")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        """Validate positive integers."""
        if value <= 0:
            raise ValueError("Los valores de configuración de BD deben ser positivos")
        return value

    @field_validator("gemini_timeout_seconds", "gemini_max_media_bytes")
    @classmethod
    def validate_positive_gemini_values(cls, value: int) -> int:
        """Validate positive Gemini numeric settings."""
        if value <= 0:
            raise ValueError("Gemini numeric settings must be positive")
        return value

    @field_validator("gemini_model")
    @classmethod
    def validate_gemini_model(cls, value: str) -> str:
        """Validate Gemini model name."""
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("GEMINI_MODEL cannot be empty")
        return normalized_value

    @field_validator("gemini_fallback_models")
    @classmethod
    def validate_gemini_fallback_models(cls, value: str) -> str:
        """Validate Gemini fallback model list format."""
        normalized_models = [model.strip() for model in value.split(",") if model.strip()]
        return ",".join(normalized_models)
    
    @field_validator("assignment_timeout_minutes", "assignment_max_attempts", "assignment_retry_delay_seconds")
    @classmethod
    def validate_assignment_config(cls, value: int) -> int:
        """Validate assignment configuration values."""
        if value <= 0:
            raise ValueError("Assignment configuration values must be positive")
        return value
    
    @field_validator("assignment_timeout_high_priority", "assignment_timeout_medium_priority", "assignment_timeout_low_priority")
    @classmethod
    def validate_assignment_timeouts(cls, value: int) -> int:
        """Validate assignment timeout values."""
        if value <= 0:
            raise ValueError("Assignment timeout values must be positive")
        if value > 60:
            raise ValueError("Assignment timeout values should not exceed 60 minutes")
        return value
    
    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str) -> str:
        """Validate Supabase URL format."""
        if not value:
            raise ValueError("SUPABASE_URL es requerida")
        if not value.startswith("https://"):
            raise ValueError("SUPABASE_URL debe comenzar con https://")
        if ".supabase.co" not in value:
            raise ValueError("SUPABASE_URL debe ser una URL válida de Supabase")
        return value
    
    @field_validator("supabase_service_role_key")
    @classmethod
    def validate_supabase_service_role_key(cls, value: str) -> str:
        """Validate Supabase service role key."""
        if not value:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY es requerida")
        if len(value) < 100:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY parece inválida (muy corta)")
        if not value.startswith("eyJ"):
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY debe ser un JWT válido")
        return value
    
    @property
    def sqlalchemy_database_url(self) -> str:
        """Get SQLAlchemy database URL with proper async driver."""
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL no está configurada. "
                "Agrega la URL de conexión de Supabase en .env"
            )

        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url

        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)

        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        return self.database_url

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS origins as list."""
        origins = [
            origin.strip() 
            for origin in self.cors_origins_raw.split(",") 
            if origin.strip()
        ]

        if not origins:
            return ["*"]

        return origins
    
    @property
    def whitelist_ips(self) -> list[str]:
        """Get rate limit whitelist IPs as list."""
        return [
            ip.strip() 
            for ip in self.rate_limit_whitelist_ips_raw.split(",") 
            if ip.strip()
        ]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    # Email provider compatibility properties
    @property
    def smtp_from_email(self) -> str:
        """Alias for email_from_address."""
        return self.email_from_address
    
    @property
    def smtp_from_name(self) -> str:
        """Alias for email_from_name."""
        return self.email_from_name
    
    @property
    def smtp_server(self) -> str:
        """Alias for brevo_smtp_host."""
        return self.brevo_smtp_host
    
    @property
    def smtp_port(self) -> int:
        """Alias for brevo_smtp_port."""
        return self.brevo_smtp_port
    
    @property
    def smtp_username(self) -> str:
        """Alias for brevo_smtp_user."""
        return self.brevo_smtp_user
    
    @property
    def smtp_password(self) -> str:
        """Alias for brevo_smtp_password."""
        return self.brevo_smtp_password

    @property
    def is_gemini_enabled(self) -> bool:
        """Check whether Gemini integration is enabled."""
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    @property
    def is_firebase_enabled(self) -> bool:
        """Check whether Firebase integration is enabled."""
        return bool(
            self.firebase_project_id and 
            self.firebase_project_id.strip() and
            self.push_notifications_enabled
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
    return Settings()


# Alias for backward compatibility
settings = get_settings()
