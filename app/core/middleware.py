"""
Core middleware module with request ID, logging, and error handling.
"""
import json
import logging
import time
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .exceptions import AppException
from .logging import get_logger
from .responses import create_error_response

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add unique request ID to each request."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request state and response headers."""
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging."""
    
    EXCLUDED_PATHS = {
        "/",
        "/health",
        "/db/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response information."""
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        start_time = time.time()
        request_id = getattr(request.state, "request_id", "unknown")
        
        # Log request
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params) if request.query_params else None,
            request_id=request_id,
            ip_address=self._get_ip_address(request),
            user_agent=request.headers.get("user-agent", "")[:200],
        )
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time_ms=round(process_time * 1000, 2),
                request_id=request_id,
            )
            
            return response
            
        except Exception as exc:
            process_time = time.time() - start_time
            
            # Log error
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                process_time_ms=round(process_time * 1000, 2),
                request_id=request_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    def _get_ip_address(self, request: Request) -> str:
        """Extract client IP address."""
        # Try to get from headers (if behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Get from client
        if request.client:
            return request.client.host
        
        return "unknown"


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for centralized error handling."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle exceptions and return standardized error responses."""
        try:
            return await call_next(request)
        except AppException as exc:
            # Handle custom application exceptions
            request_id = getattr(request.state, "request_id", str(uuid4()))
            
            logger.warning(
                "Application exception",
                error_code=exc.code,
                error_message=exc.message,
                status_code=exc.status_code,
                request_id=request_id,
                details=exc.details,
            )
            
            response = create_error_response(
                message=exc.message,
                code=exc.code,
                status_code=exc.status_code,
                details=exc.details,
                request_id=request_id,
            )
            
            # Add CORS headers manually
            origin = request.headers.get("origin")
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "*"
            
            return response
            
        except Exception as exc:
            # Handle unexpected exceptions
            request_id = getattr(request.state, "request_id", str(uuid4()))
            
            logger.error(
                "Unexpected exception",
                error=str(exc),
                request_id=request_id,
                exc_info=True,
            )
            
            response = create_error_response(
                message="Error interno del servidor",
                code="INTERNAL_SERVER_ERROR",
                status_code=500,
                request_id=request_id,
            )
            
            # Add CORS headers manually
            origin = request.headers.get("origin")
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "*"
            
            return response


class AuditMiddleware(BaseHTTPMiddleware):
    """Enhanced audit middleware with better error handling and performance."""
    
    EXCLUDED_PATHS = {
        "/",
        "/health",
        "/db/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/metrics",
    }
    
    AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    
    def __init__(self, app: ASGIApp, audit_all_methods: bool = False):
        """
        Initialize audit middleware.
        
        Args:
            app: ASGI application
            audit_all_methods: If True, audit GET requests too
        """
        super().__init__(app)
        self.audit_all_methods = audit_all_methods
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log to audit."""
        if not self._should_audit(request):
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract request information
        user_id = self._get_user_id(request)
        ip_address = self._get_ip_address(request)
        user_agent = request.headers.get("user-agent", "")[:500]
        request_id = getattr(request.state, "request_id", str(uuid4()))
        
        # Process request
        response = None
        error = None
        status_code = 500
        
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            error = str(e)
            raise
        finally:
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log audit in background (don't block request)
            try:
                await self._log_request_async(
                    method=request.method,
                    path=request.url.path,
                    user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status_code=status_code,
                    process_time=process_time,
                    error=error,
                    query_params=dict(request.query_params) if request.query_params else None,
                    request_id=request_id,
                )
            except Exception as e:
                # Don't fail request if audit logging fails
                logger.error(
                    "Failed to log audit",
                    error=str(e),
                    request_id=request_id,
                    exc_info=True,
                )
        
        return response
    
    def _should_audit(self, request: Request) -> bool:
        """Determine if request should be audited."""
        if request.url.path in self.EXCLUDED_PATHS:
            return False
        
        if request.url.path.startswith("/static"):
            return False
        
        if not self.audit_all_methods:
            return request.method in self.AUDITED_METHODS
        
        return True
    
    def _get_user_id(self, request: Request) -> int | None:
        """Extract user ID from request if available."""
        # Try to get from state (if auth dependency was used)
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "id"):
            return user.id
        
        # Try to get from token payload
        token_payload = getattr(request.state, "token_payload", None)
        if token_payload and hasattr(token_payload, "sub"):
            try:
                return int(token_payload.sub)
            except (ValueError, TypeError):
                pass
        
        return None
    
    def _get_ip_address(self, request: Request) -> str:
        """Extract client IP address."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def _log_request_async(
        self,
        method: str,
        path: str,
        user_id: int | None,
        ip_address: str,
        user_agent: str,
        status_code: int,
        process_time: float,
        error: str | None = None,
        query_params: dict | None = None,
        request_id: str | None = None,
    ) -> None:
        """Log request to audit system asynchronously."""
        # Import here to avoid circular imports
        from ..shared.dependencies.database import get_async_session
        from ..models.audit_log import AuditLog
        
        try:
            async with get_async_session() as session:
                action = self._determine_action(method, path, status_code)
                
                details = {
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "process_time_ms": round(process_time * 1000, 2),
                    "request_id": request_id,
                }
                
                if query_params:
                    details["query_params"] = query_params
                
                if error:
                    details["error"] = error
                
                audit_log = AuditLog(
                    user_id=user_id,
                    action=action,
                    resource_type=self._extract_resource_type(path),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=json.dumps(details, ensure_ascii=False),
                )
                
                session.add(audit_log)
                await session.commit()
                
        except Exception as e:
            logger.error(
                "Failed to save audit log",
                error=str(e),
                request_id=request_id,
                exc_info=True,
            )
    
    def _determine_action(self, method: str, path: str, status_code: int) -> str:
        """Determine action based on HTTP method and path."""
        if status_code >= 400:
            return f"{method.lower()}_failed"
        
        # Specific route mappings
        if "/login" in path:
            return "login" if status_code < 400 else "login_failed"
        elif "/register" in path:
            return "register"
        elif "/logout" in path:
            return "logout"
        elif "/password" in path:
            if "forgot" in path or "reset/request" in path:
                return "password_reset_request"
            elif "reset" in path:
                return "password_reset"
            elif "change" in path:
                return "password_change"
        elif "/2fa" in path:
            if "enable" in path:
                return "2fa_enabled"
            elif "disable" in path:
                return "2fa_disabled"
            elif "verify" in path:
                return "2fa_verified"
        
        # Generic action based on HTTP method
        action_map = {
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
            "GET": "read",
        }
        
        return action_map.get(method, method.lower())
    
    def _extract_resource_type(self, path: str) -> str | None:
        """Extract resource type from path."""
        if "/clients" in path:
            return "client"
        elif "/workshops" in path:
            return "workshop"
        elif "/technicians" in path:
            return "technician"
        elif "/administrators" in path:
            return "administrator"
        elif "/incidents" in path:
            return "incident"
        elif "/vehicles" in path:
            return "vehicle"
        elif "/services" in path:
            return "service"
        elif "/auth" in path or "/password" in path or "/2fa" in path:
            return "user"
        
        return None