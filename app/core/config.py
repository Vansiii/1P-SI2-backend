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
    app_name: str = "Sistema de Gestión de Talleres"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=True, alias="DEBUG")
    
    # Database
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    
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
    
    @field_validator("db_pool_size", "db_max_overflow", "db_pool_timeout")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        """Validate positive integers."""
        if value <= 0:
            raise ValueError("Los valores de configuración de BD deben ser positivos")
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()