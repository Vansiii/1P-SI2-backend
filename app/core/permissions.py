"""
Sistema de permisos y autorización basado en roles y casos de uso.

Mapeo de actores del sistema:
- A1: Cliente (Usuario de la App Móvil)
- A2: Taller Mecánico (Usuario de la App Web)
- A3: Administrador del Sistema (Usuario de la App Web)
- A4: Técnico de Taller (Usuario de la App Móvil)
- A5: Sistema/IA (Actor interno)
"""

from enum import Enum
from typing import Any

from fastapi import HTTPException, status


class UserRole(str, Enum):
    """Roles de usuario en el sistema."""
    CLIENT = "client"  # A1
    WORKSHOP = "workshop"  # A2
    TECHNICIAN = "technician"  # A4
    ADMINISTRATOR = "admin"  # A3 - Cambiado de "administrator" a "admin" para coincidir con BD
    SYSTEM = "system"  # A5 (interno)


class Permission(str, Enum):
    """
    Permisos del sistema basados en casos de uso.
    Formato: MODULO_ACCION o CU##_NOMBRE
    """
    
    # ========== MÓDULO 1: AUTENTICACIÓN Y SEGURIDAD ==========
    # CU01: Gestionar Autenticación (todos los usuarios)
    AUTH_REGISTER = "auth:register"
    AUTH_LOGIN = "auth:login"
    AUTH_LOGOUT = "auth:logout"
    AUTH_REFRESH_TOKEN = "auth:refresh_token"
    
    # CU02: Gestionar Contraseña
    PASSWORD_CHANGE = "password:change"
    PASSWORD_FORGOT = "password:forgot"
    PASSWORD_RESET = "password:reset"
    
    # ========== MÓDULO 2: GESTIÓN DE EMERGENCIAS (APP MÓVIL - CLIENTE) ==========
    # CU03: Reportar Emergencia Vehicular
    EMERGENCY_CREATE = "emergency:create"
    EMERGENCY_UPLOAD_EVIDENCE = "emergency:upload_evidence"
    
    # CU04: Consultar y Seguir Solicitud
    EMERGENCY_VIEW_OWN = "emergency:view_own"
    EMERGENCY_TRACK = "emergency:track"
    EMERGENCY_VIEW_HISTORY = "emergency:view_history"
    
    # CU05: Comunicarse con el Taller
    CHAT_CLIENT_TO_WORKSHOP = "chat:client_to_workshop"
    
    # CU06: Calificar Servicio Recibido
    SERVICE_RATE = "service:rate"
    
    # ========== MÓDULO 3: GESTIÓN DE SOLICITUDES (APP WEB - TALLER) ==========
    # CU07: Gestionar Solicitudes Entrantes
    REQUEST_VIEW_INCOMING = "request:view_incoming"
    REQUEST_ACCEPT = "request:accept"
    REQUEST_REJECT = "request:reject"
    REQUEST_VIEW_TECHNICIANS = "request:view_technicians"
    
    # CU08: Gestionar Atención del Servicio
    SERVICE_ASSIGN_TECHNICIAN = "service:assign_technician"
    SERVICE_UPDATE_STATUS = "service:update_status"
    SERVICE_VIEW_HISTORY = "service:view_history"
    SERVICE_MANAGE_AVAILABILITY = "service:manage_availability"
    
    # CU09: Comunicarse con el Cliente
    CHAT_WORKSHOP_TO_CLIENT = "chat:workshop_to_client"
    
    # ========== MÓDULO 4: INTELIGENCIA ARTIFICIAL (SISTEMA) ==========
    # CU10: Procesar y Clasificar Incidente
    AI_PROCESS_INCIDENT = "ai:process_incident"
    AI_CLASSIFY_INCIDENT = "ai:classify_incident"
    AI_TRANSCRIBE_AUDIO = "ai:transcribe_audio"
    AI_ANALYZE_IMAGE = "ai:analyze_image"
    AI_GENERATE_SUMMARY = "ai:generate_summary"
    
    # CU11: Gestionar Caso Ambiguo
    AI_HANDLE_UNCERTAIN = "ai:handle_uncertain"
    AI_REQUEST_MORE_INFO = "ai:request_more_info"
    ADMIN_MANUAL_INTERVENTION = "admin:manual_intervention"
    
    # ========== MÓDULO 5: ASIGNACIÓN INTELIGENTE (SISTEMA) ==========
    # CU12: Asignar Técnico y Taller al Incidente
    ASSIGNMENT_AUTO_ASSIGN = "assignment:auto_assign"
    ASSIGNMENT_CALCULATE_ROUTE = "assignment:calculate_route"
    
    # CU13: Reasignar Taller
    ASSIGNMENT_REASSIGN = "assignment:reassign"
    ADMIN_FORCE_REASSIGN = "admin:force_reassign"
    
    # ========== MÓDULO 6: PAGOS Y COMISIONES ==========
    # CU14: Gestionar Pago del Cliente
    PAYMENT_PROCESS = "payment:process"
    PAYMENT_VIEW_OWN = "payment:view_own"
    PAYMENT_VIEW_RECEIPT = "payment:view_receipt"
    
    # CU15: Gestionar Comisión del Taller
    COMMISSION_CALCULATE = "commission:calculate"
    COMMISSION_VIEW_OWN = "commission:view_own"
    ADMIN_VIEW_ALL_COMMISSIONS = "admin:view_all_commissions"
    
    # ========== MÓDULO 7: NOTIFICACIONES ==========
    # CU16: Gestionar Notificaciones
    NOTIFICATION_RECEIVE = "notification:receive"
    NOTIFICATION_SEND = "notification:send"
    
    # ========== MÓDULO 8: GESTIÓN DE VEHÍCULOS Y PERFILES ==========
    # CU17: Gestionar Vehículos
    VEHICLE_CREATE = "vehicle:create"
    VEHICLE_UPDATE = "vehicle:update"
    VEHICLE_DELETE = "vehicle:delete"
    VEHICLE_VIEW_OWN = "vehicle:view_own"
    
    # CU18: Gestionar Perfil de Usuario y Taller
    PROFILE_VIEW_OWN = "profile:view_own"
    PROFILE_UPDATE_OWN = "profile:update_own"
    PROFILE_DELETE_OWN = "profile:delete_own"
    
    # CU19: Gestionar Técnicos del Taller
    TECHNICIAN_CREATE = "technician:create"
    TECHNICIAN_UPDATE = "technician:update"
    TECHNICIAN_DELETE = "technician:delete"
    TECHNICIAN_VIEW_LOCATION = "technician:view_location"
    TECHNICIAN_VIEW_OWN_WORKSHOP = "technician:view_own_workshop"
    
    # ========== MÓDULO 9: REPORTES Y MÉTRICAS ==========
    # CU20: Generar y Exportar Reportes
    REPORT_VIEW_OPERATIONAL = "report:view_operational"
    REPORT_VIEW_FINANCIAL = "report:view_financial"
    REPORT_VIEW_PERFORMANCE = "report:view_performance"
    REPORT_EXPORT_PDF = "report:export_pdf"
    REPORT_EXPORT_EXCEL = "report:export_excel"
    REPORT_VIEW_ALL = "report:view_all"
    
    # ========== MÓDULO 10: ADMINISTRACIÓN GENERAL ==========
    # CU21: Gestionar Usuarios y Talleres
    ADMIN_MANAGE_USERS = "admin:manage_users"
    ADMIN_MANAGE_WORKSHOPS = "admin:manage_workshops"
    ADMIN_CREATE_USER = "admin:create_user"
    ADMIN_UPDATE_USER = "admin:update_user"
    ADMIN_DELETE_USER = "admin:delete_user"
    ADMIN_ENABLE_DISABLE_USER = "admin:enable_disable_user"
    
    # CU22: Monitorear Sistema en Tiempo Real
    ADMIN_MONITOR_SYSTEM = "admin:monitor_system"
    ADMIN_VIEW_ACTIVE_INCIDENTS = "admin:view_active_incidents"
    ADMIN_VIEW_WORKSHOP_AVAILABILITY = "admin:view_workshop_availability"
    
    # CU23: Configurar Sistema
    ADMIN_CONFIGURE_SYSTEM = "admin:configure_system"
    ADMIN_CONFIGURE_ASSIGNMENT_ENGINE = "admin:configure_assignment_engine"
    ADMIN_CONFIGURE_CATEGORIES = "admin:configure_categories"
    ADMIN_CONFIGURE_COMMISSION = "admin:configure_commission"
    ADMIN_VIEW_AUDIT_LOG = "admin:view_audit_log"
    ADMIN_MANAGE_PERMISSIONS = "admin:manage_permissions"  # Gestionar permisos de roles


# Mapeo de permisos por rol basado en casos de uso
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    # A1: Cliente (Usuario de la App Móvil)
    UserRole.CLIENT: {
        # CU01: Autenticación (todos)
        Permission.AUTH_REGISTER,
        Permission.AUTH_LOGIN,
        Permission.AUTH_LOGOUT,
        Permission.AUTH_REFRESH_TOKEN,
        
        # CU02: Gestionar Contraseña
        Permission.PASSWORD_CHANGE,
        Permission.PASSWORD_FORGOT,
        Permission.PASSWORD_RESET,
        
        # CU03: Reportar Emergencia Vehicular
        Permission.EMERGENCY_CREATE,
        Permission.EMERGENCY_UPLOAD_EVIDENCE,
        
        # CU04: Consultar y Seguir Solicitud
        Permission.EMERGENCY_VIEW_OWN,
        Permission.EMERGENCY_TRACK,
        Permission.EMERGENCY_VIEW_HISTORY,
        
        # CU05: Comunicarse con el Taller
        Permission.CHAT_CLIENT_TO_WORKSHOP,
        
        # CU06: Calificar Servicio Recibido
        Permission.SERVICE_RATE,
        
        # CU14: Gestionar Pago del Cliente
        Permission.PAYMENT_PROCESS,
        Permission.PAYMENT_VIEW_OWN,
        Permission.PAYMENT_VIEW_RECEIPT,
        
        # CU16: Gestionar Notificaciones
        Permission.NOTIFICATION_RECEIVE,
        
        # CU17: Gestionar Vehículos
        Permission.VEHICLE_CREATE,
        Permission.VEHICLE_UPDATE,
        Permission.VEHICLE_DELETE,
        Permission.VEHICLE_VIEW_OWN,
        
        # CU18: Gestionar Perfil
        Permission.PROFILE_VIEW_OWN,
        Permission.PROFILE_UPDATE_OWN,
        Permission.PROFILE_DELETE_OWN,
    },
    
    # A2: Taller Mecánico (Usuario de la App Web)
    UserRole.WORKSHOP: {
        # CU01: Autenticación
        Permission.AUTH_REGISTER,
        Permission.AUTH_LOGIN,
        Permission.AUTH_LOGOUT,
        Permission.AUTH_REFRESH_TOKEN,
        
        # CU02: Gestionar Contraseña
        Permission.PASSWORD_CHANGE,
        Permission.PASSWORD_FORGOT,
        Permission.PASSWORD_RESET,
        
        # CU07: Gestionar Solicitudes Entrantes
        Permission.REQUEST_VIEW_INCOMING,
        Permission.REQUEST_ACCEPT,
        Permission.REQUEST_REJECT,
        Permission.REQUEST_VIEW_TECHNICIANS,
        Permission.EMERGENCY_VIEW_OWN,  # Necesario para ver incidentes asignados
        
        # CU08: Gestionar Atención del Servicio
        Permission.SERVICE_ASSIGN_TECHNICIAN,
        Permission.SERVICE_UPDATE_STATUS,
        Permission.SERVICE_VIEW_HISTORY,
        Permission.SERVICE_MANAGE_AVAILABILITY,
        
        # CU09: Comunicarse con el Cliente
        Permission.CHAT_WORKSHOP_TO_CLIENT,
        
        # CU15: Gestionar Comisión del Taller
        Permission.COMMISSION_VIEW_OWN,
        
        # CU16: Gestionar Notificaciones
        Permission.NOTIFICATION_RECEIVE,
        Permission.NOTIFICATION_SEND,
        
        # CU18: Gestionar Perfil
        Permission.PROFILE_VIEW_OWN,
        Permission.PROFILE_UPDATE_OWN,
        
        # CU19: Gestionar Técnicos del Taller
        Permission.TECHNICIAN_CREATE,
        Permission.TECHNICIAN_UPDATE,
        Permission.TECHNICIAN_DELETE,
        Permission.TECHNICIAN_VIEW_LOCATION,
        Permission.TECHNICIAN_VIEW_OWN_WORKSHOP,
    },
    
    # A4: Técnico de Taller (Usuario de la App Móvil)
    UserRole.TECHNICIAN: {
        # CU01: Autenticación
        Permission.AUTH_LOGIN,
        Permission.AUTH_LOGOUT,
        Permission.AUTH_REFRESH_TOKEN,
        
        # CU02: Gestionar Contraseña
        Permission.PASSWORD_CHANGE,
        
        # CU08: Gestionar Atención del Servicio (limitado)
        Permission.SERVICE_UPDATE_STATUS,
        Permission.SERVICE_VIEW_HISTORY,
        
        # CU09: Comunicarse con el Cliente
        Permission.CHAT_WORKSHOP_TO_CLIENT,
        
        # CU16: Gestionar Notificaciones
        Permission.NOTIFICATION_RECEIVE,
        
        # CU18: Gestionar Perfil
        Permission.PROFILE_VIEW_OWN,
        Permission.PROFILE_UPDATE_OWN,
    },
    
    # A3: Administrador del Sistema (Usuario de la App Web)
    UserRole.ADMINISTRATOR: {
        # CU01: Autenticación
        Permission.AUTH_LOGIN,
        Permission.AUTH_LOGOUT,
        Permission.AUTH_REFRESH_TOKEN,
        
        # CU02: Gestionar Contraseña
        Permission.PASSWORD_CHANGE,
        Permission.PASSWORD_FORGOT,
        Permission.PASSWORD_RESET,
        
        # CU11: Gestionar Caso Ambiguo
        Permission.ADMIN_MANUAL_INTERVENTION,
        
        # CU13: Reasignar Taller
        Permission.ADMIN_FORCE_REASSIGN,
        
        # CU15: Gestionar Comisión del Taller
        Permission.ADMIN_VIEW_ALL_COMMISSIONS,
        
        # CU16: Gestionar Notificaciones
        Permission.NOTIFICATION_RECEIVE,
        Permission.NOTIFICATION_SEND,
        
        # CU18: Gestionar Perfil
        Permission.PROFILE_VIEW_OWN,
        Permission.PROFILE_UPDATE_OWN,
        
        # CU20: Generar y Exportar Reportes
        Permission.REPORT_VIEW_OPERATIONAL,
        Permission.REPORT_VIEW_FINANCIAL,
        Permission.REPORT_VIEW_PERFORMANCE,
        Permission.REPORT_EXPORT_PDF,
        Permission.REPORT_EXPORT_EXCEL,
        Permission.REPORT_VIEW_ALL,
        
        # CU21: Gestionar Usuarios y Talleres
        Permission.ADMIN_MANAGE_USERS,
        Permission.ADMIN_MANAGE_WORKSHOPS,
        Permission.ADMIN_CREATE_USER,
        Permission.ADMIN_UPDATE_USER,
        Permission.ADMIN_DELETE_USER,
        Permission.ADMIN_ENABLE_DISABLE_USER,
        
        # CU22: Monitorear Sistema en Tiempo Real
        Permission.ADMIN_MONITOR_SYSTEM,
        Permission.ADMIN_VIEW_ACTIVE_INCIDENTS,
        Permission.ADMIN_VIEW_WORKSHOP_AVAILABILITY,
        
        # CU23: Configurar Sistema
        Permission.ADMIN_CONFIGURE_SYSTEM,
        Permission.ADMIN_CONFIGURE_ASSIGNMENT_ENGINE,
        Permission.ADMIN_CONFIGURE_CATEGORIES,
        Permission.ADMIN_CONFIGURE_COMMISSION,
        Permission.ADMIN_VIEW_AUDIT_LOG,
        Permission.ADMIN_MANAGE_PERMISSIONS,  # Gestionar permisos de roles
        
        # Permisos adicionales para monitoreo y gestión
        Permission.VEHICLE_VIEW_OWN,  # Ver vehículos de todos los clientes
        Permission.EMERGENCY_VIEW_OWN,  # Ver incidentes de todos los clientes
        Permission.REQUEST_VIEW_INCOMING,  # Ver solicitudes entrantes
    },
    
    # A5: Sistema/IA (Actor interno)
    UserRole.SYSTEM: {
        # CU10: Procesar y Clasificar Incidente
        Permission.AI_PROCESS_INCIDENT,
        Permission.AI_CLASSIFY_INCIDENT,
        Permission.AI_TRANSCRIBE_AUDIO,
        Permission.AI_ANALYZE_IMAGE,
        Permission.AI_GENERATE_SUMMARY,
        
        # CU11: Gestionar Caso Ambiguo
        Permission.AI_HANDLE_UNCERTAIN,
        Permission.AI_REQUEST_MORE_INFO,
        
        # CU12: Asignar Técnico y Taller
        Permission.ASSIGNMENT_AUTO_ASSIGN,
        Permission.ASSIGNMENT_CALCULATE_ROUTE,
        
        # CU13: Reasignar Taller
        Permission.ASSIGNMENT_REASSIGN,
        
        # CU15: Gestionar Comisión
        Permission.COMMISSION_CALCULATE,
        
        # CU16: Notificaciones
        Permission.NOTIFICATION_SEND,
    },
}


def get_role_permissions(role: UserRole) -> set[Permission]:
    """Obtiene todos los permisos asociados a un rol."""
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(user_role: UserRole, required_permission: Permission) -> bool:
    """Verifica si un rol tiene un permiso específico."""
    role_perms = get_role_permissions(user_role)
    return required_permission in role_perms


def check_permission(user_role: str, required_permission: Permission) -> None:
    """
    Verifica que el usuario tenga el permiso requerido.
    Lanza HTTPException si no tiene permiso.
    """
    try:
        role = UserRole(user_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol de usuario inválido: {user_role}",
        )
    
    if not has_permission(role, required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permiso para realizar esta acción. Permiso requerido: {required_permission.value}",
        )


def check_any_permission(user_role: str, required_permissions: list[Permission]) -> None:
    """
    Verifica que el usuario tenga al menos uno de los permisos requeridos.
    Lanza HTTPException si no tiene ninguno.
    """
    try:
        role = UserRole(user_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol de usuario inválido: {user_role}",
        )
    
    role_perms = get_role_permissions(role)
    if not any(perm in role_perms for perm in required_permissions):
        perms_str = ", ".join(p.value for p in required_permissions)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permiso para realizar esta acción. Se requiere uno de: {perms_str}",
        )


def check_all_permissions(user_role: str, required_permissions: list[Permission]) -> None:
    """
    Verifica que el usuario tenga todos los permisos requeridos.
    Lanza HTTPException si falta alguno.
    """
    try:
        role = UserRole(user_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol de usuario inválido: {user_role}",
        )
    
    role_perms = get_role_permissions(role)
    missing_perms = [p for p in required_permissions if p not in role_perms]
    
    if missing_perms:
        perms_str = ", ".join(p.value for p in missing_perms)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes todos los permisos requeridos. Faltan: {perms_str}",
        )


def get_user_permissions_list(user_role: str) -> list[str]:
    """Retorna lista de permisos de un usuario en formato string."""
    try:
        role = UserRole(user_role)
        return [perm.value for perm in get_role_permissions(role)]
    except ValueError:
        return []
