"""
Sistema de métricas con Prometheus.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from typing import Callable
import time

# Métricas de requests HTTP
http_requests_total = Counter(
    'http_requests_total',
    'Total de requests HTTP',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'Duración de requests HTTP en segundos',
    ['method', 'endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Número de requests HTTP en progreso',
    ['method', 'endpoint']
)

# Métricas de autenticación
auth_attempts_total = Counter(
    'auth_attempts_total',
    'Total de intentos de autenticación',
    ['user_type', 'status']
)

auth_failures_total = Counter(
    'auth_failures_total',
    'Total de fallos de autenticación',
    ['user_type', 'reason']
)

auth_lockouts_total = Counter(
    'auth_lockouts_total',
    'Total de cuentas bloqueadas',
    ['user_type']
)

# Métricas de tokens
tokens_created_total = Counter(
    'tokens_created_total',
    'Total de tokens creados',
    ['token_type', 'user_type']
)

tokens_revoked_total = Counter(
    'tokens_revoked_total',
    'Total de tokens revocados',
    ['token_type', 'user_type']
)

tokens_active = Gauge(
    'tokens_active',
    'Número de tokens activos',
    ['token_type']
)

# Métricas de base de datos
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Duración de queries de base de datos en segundos',
    ['operation'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0)
)

db_connections_active = Gauge(
    'db_connections_active',
    'Número de conexiones activas a la base de datos'
)

db_connections_idle = Gauge(
    'db_connections_idle',
    'Número de conexiones idle en el pool'
)

# Métricas de usuarios
users_registered_total = Counter(
    'users_registered_total',
    'Total de usuarios registrados',
    ['user_type']
)

users_active = Gauge(
    'users_active',
    'Número de usuarios activos',
    ['user_type']
)

# Métricas de 2FA
two_factor_enabled_total = Counter(
    'two_factor_enabled_total',
    'Total de usuarios con 2FA habilitado',
    ['user_type']
)

two_factor_verifications_total = Counter(
    'two_factor_verifications_total',
    'Total de verificaciones 2FA',
    ['user_type', 'status']
)

# Métricas de emails
emails_sent_total = Counter(
    'emails_sent_total',
    'Total de emails enviados',
    ['template', 'status']
)

emails_failed_total = Counter(
    'emails_failed_total',
    'Total de emails fallidos',
    ['template', 'reason']
)

# Métricas de rate limiting
rate_limit_exceeded_total = Counter(
    'rate_limit_exceeded_total',
    'Total de requests bloqueados por rate limiting',
    ['endpoint']
)

# Métricas de errores
errors_total = Counter(
    'errors_total',
    'Total de errores',
    ['error_type', 'endpoint']
)

exceptions_total = Counter(
    'exceptions_total',
    'Total de excepciones',
    ['exception_type']
)


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware para recolectar métricas de requests HTTP.
    """
    method = request.method
    endpoint = request.url.path
    
    # Incrementar requests en progreso
    http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
    
    # Medir duración
    start_time = time.time()
    
    try:
        response = await call_next(request)
        status = response.status_code
        
        # Registrar métricas
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status
        ).inc()
        
        duration = time.time() - start_time
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        return response
        
    except Exception as e:
        # Registrar error
        errors_total.labels(
            error_type=type(e).__name__,
            endpoint=endpoint
        ).inc()
        
        exceptions_total.labels(
            exception_type=type(e).__name__
        ).inc()
        
        raise
        
    finally:
        # Decrementar requests en progreso
        http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()


def get_metrics() -> tuple[bytes, str]:
    """
    Obtener métricas en formato Prometheus.
    
    Returns:
        Tuple con (contenido, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST


# Funciones helper para registrar métricas específicas

def record_auth_attempt(user_type: str, success: bool):
    """Registrar intento de autenticación."""
    status = "success" if success else "failure"
    auth_attempts_total.labels(user_type=user_type, status=status).inc()


def record_auth_failure(user_type: str, reason: str):
    """Registrar fallo de autenticación."""
    auth_failures_total.labels(user_type=user_type, reason=reason).inc()


def record_auth_lockout(user_type: str):
    """Registrar bloqueo de cuenta."""
    auth_lockouts_total.labels(user_type=user_type).inc()


def record_token_created(token_type: str, user_type: str):
    """Registrar creación de token."""
    tokens_created_total.labels(token_type=token_type, user_type=user_type).inc()


def record_token_revoked(token_type: str, user_type: str):
    """Registrar revocación de token."""
    tokens_revoked_total.labels(token_type=token_type, user_type=user_type).inc()


def record_user_registered(user_type: str):
    """Registrar registro de usuario."""
    users_registered_total.labels(user_type=user_type).inc()


def record_2fa_enabled(user_type: str):
    """Registrar habilitación de 2FA."""
    two_factor_enabled_total.labels(user_type=user_type).inc()


def record_2fa_verification(user_type: str, success: bool):
    """Registrar verificación de 2FA."""
    status = "success" if success else "failure"
    two_factor_verifications_total.labels(user_type=user_type, status=status).inc()


def record_email_sent(template: str, success: bool):
    """Registrar envío de email."""
    status = "success" if success else "failure"
    emails_sent_total.labels(template=template, status=status).inc()


def record_email_failed(template: str, reason: str):
    """Registrar fallo de email."""
    emails_failed_total.labels(template=template, reason=reason).inc()


def record_rate_limit_exceeded(endpoint: str):
    """Registrar exceso de rate limit."""
    rate_limit_exceeded_total.labels(endpoint=endpoint).inc()


def record_db_query(operation: str, duration: float):
    """Registrar query de base de datos."""
    db_query_duration_seconds.labels(operation=operation).observe(duration)


def update_db_connections(active: int, idle: int):
    """Actualizar métricas de conexiones de base de datos."""
    db_connections_active.set(active)
    db_connections_idle.set(idle)


def update_active_users(user_type: str, count: int):
    """Actualizar número de usuarios activos."""
    users_active.labels(user_type=user_type).set(count)


def update_active_tokens(token_type: str, count: int):
    """Actualizar número de tokens activos."""
    tokens_active.labels(token_type=token_type).set(count)
