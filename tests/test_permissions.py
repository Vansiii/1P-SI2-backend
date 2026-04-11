"""
Tests para el sistema de permisos y autorización.
"""

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    Permission,
    UserRole,
    check_all_permissions,
    check_any_permission,
    check_permission,
    get_role_permissions,
    get_user_permissions_list,
    has_permission,
)


class TestRolePermissions:
    """Tests para verificar permisos por rol."""
    
    def test_client_permissions(self):
        """Verificar que clientes tengan permisos correctos."""
        client_perms = get_role_permissions(UserRole.CLIENT)
        
        # Debe tener permisos de emergencias
        assert Permission.EMERGENCY_CREATE in client_perms
        assert Permission.EMERGENCY_VIEW_OWN in client_perms
        assert Permission.EMERGENCY_TRACK in client_perms
        
        # Debe tener permisos de vehículos
        assert Permission.VEHICLE_CREATE in client_perms
        assert Permission.VEHICLE_UPDATE in client_perms
        
        # Debe tener permisos de perfil
        assert Permission.PROFILE_VIEW_OWN in client_perms
        assert Permission.PROFILE_UPDATE_OWN in client_perms
        
        # NO debe tener permisos de administración
        assert Permission.ADMIN_MANAGE_USERS not in client_perms
        assert Permission.ADMIN_CONFIGURE_SYSTEM not in client_perms
    
    def test_workshop_permissions(self):
        """Verificar que talleres tengan permisos correctos."""
        workshop_perms = get_role_permissions(UserRole.WORKSHOP)
        
        # Debe tener permisos de solicitudes
        assert Permission.REQUEST_VIEW_INCOMING in workshop_perms
        assert Permission.REQUEST_ACCEPT in workshop_perms
        assert Permission.REQUEST_REJECT in workshop_perms
        
        # Debe tener permisos de servicio
        assert Permission.SERVICE_ASSIGN_TECHNICIAN in workshop_perms
        assert Permission.SERVICE_UPDATE_STATUS in workshop_perms
        
        # Debe tener permisos de técnicos
        assert Permission.TECHNICIAN_CREATE in workshop_perms
        assert Permission.TECHNICIAN_UPDATE in workshop_perms
        
        # NO debe tener permisos de cliente
        assert Permission.EMERGENCY_CREATE not in workshop_perms
        assert Permission.VEHICLE_CREATE not in workshop_perms
    
    def test_technician_permissions(self):
        """Verificar que técnicos tengan permisos correctos."""
        tech_perms = get_role_permissions(UserRole.TECHNICIAN)
        
        # Debe tener permisos limitados de servicio
        assert Permission.SERVICE_UPDATE_STATUS in tech_perms
        
        # Debe tener permisos de chat
        assert Permission.CHAT_WORKSHOP_TO_CLIENT in tech_perms
        
        # NO debe tener permisos de asignación
        assert Permission.SERVICE_ASSIGN_TECHNICIAN not in tech_perms
        
        # NO debe tener permisos de gestión de técnicos
        assert Permission.TECHNICIAN_CREATE not in tech_perms
    
    def test_administrator_permissions(self):
        """Verificar que administradores tengan permisos correctos."""
        admin_perms = get_role_permissions(UserRole.ADMINISTRATOR)
        
        # Debe tener permisos de administración
        assert Permission.ADMIN_MANAGE_USERS in admin_perms
        assert Permission.ADMIN_MANAGE_WORKSHOPS in admin_perms
        assert Permission.ADMIN_CONFIGURE_SYSTEM in admin_perms
        assert Permission.ADMIN_MONITOR_SYSTEM in admin_perms
        
        # Debe tener permisos de reportes
        assert Permission.REPORT_VIEW_ALL in admin_perms
        assert Permission.REPORT_EXPORT_PDF in admin_perms
        
        # Debe tener permisos de intervención manual
        assert Permission.ADMIN_MANUAL_INTERVENTION in admin_perms
        assert Permission.ADMIN_FORCE_REASSIGN in admin_perms
    
    def test_system_permissions(self):
        """Verificar que el sistema tenga permisos correctos."""
        system_perms = get_role_permissions(UserRole.SYSTEM)
        
        # Debe tener permisos de IA
        assert Permission.AI_PROCESS_INCIDENT in system_perms
        assert Permission.AI_CLASSIFY_INCIDENT in system_perms
        assert Permission.AI_TRANSCRIBE_AUDIO in system_perms
        
        # Debe tener permisos de asignación
        assert Permission.ASSIGNMENT_AUTO_ASSIGN in system_perms
        assert Permission.ASSIGNMENT_CALCULATE_ROUTE in system_perms


class TestHasPermission:
    """Tests para la función has_permission."""
    
    def test_client_can_create_emergency(self):
        """Cliente puede crear emergencias."""
        assert has_permission(UserRole.CLIENT, Permission.EMERGENCY_CREATE)
    
    def test_client_cannot_manage_users(self):
        """Cliente no puede gestionar usuarios."""
        assert not has_permission(UserRole.CLIENT, Permission.ADMIN_MANAGE_USERS)
    
    def test_workshop_can_accept_requests(self):
        """Taller puede aceptar solicitudes."""
        assert has_permission(UserRole.WORKSHOP, Permission.REQUEST_ACCEPT)
    
    def test_workshop_cannot_create_emergency(self):
        """Taller no puede crear emergencias."""
        assert not has_permission(UserRole.WORKSHOP, Permission.EMERGENCY_CREATE)
    
    def test_admin_can_configure_system(self):
        """Administrador puede configurar sistema."""
        assert has_permission(UserRole.ADMINISTRATOR, Permission.ADMIN_CONFIGURE_SYSTEM)
    
    def test_technician_can_update_status(self):
        """Técnico puede actualizar estado."""
        assert has_permission(UserRole.TECHNICIAN, Permission.SERVICE_UPDATE_STATUS)
    
    def test_technician_cannot_assign_technician(self):
        """Técnico no puede asignar técnicos."""
        assert not has_permission(UserRole.TECHNICIAN, Permission.SERVICE_ASSIGN_TECHNICIAN)


class TestCheckPermission:
    """Tests para la función check_permission."""
    
    def test_valid_permission_passes(self):
        """Permiso válido no lanza excepción."""
        try:
            check_permission("client", Permission.EMERGENCY_CREATE)
        except HTTPException:
            pytest.fail("No debería lanzar excepción para permiso válido")
    
    def test_invalid_permission_raises(self):
        """Permiso inválido lanza HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            check_permission("client", Permission.ADMIN_MANAGE_USERS)
        
        assert exc_info.value.status_code == 403
        assert "No tienes permiso" in exc_info.value.detail
    
    def test_invalid_role_raises(self):
        """Rol inválido lanza HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            check_permission("invalid_role", Permission.EMERGENCY_CREATE)
        
        assert exc_info.value.status_code == 403
        assert "Rol de usuario inválido" in exc_info.value.detail


class TestCheckAnyPermission:
    """Tests para la función check_any_permission."""
    
    def test_has_one_permission_passes(self):
        """Tener al menos un permiso no lanza excepción."""
        try:
            check_any_permission("client", [
                Permission.EMERGENCY_CREATE,
                Permission.ADMIN_MANAGE_USERS,  # No tiene este
            ])
        except HTTPException:
            pytest.fail("No debería lanzar excepción si tiene al menos uno")
    
    def test_has_no_permissions_raises(self):
        """No tener ningún permiso lanza HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            check_any_permission("client", [
                Permission.ADMIN_MANAGE_USERS,
                Permission.ADMIN_CONFIGURE_SYSTEM,
            ])
        
        assert exc_info.value.status_code == 403
        assert "Se requiere uno de" in exc_info.value.detail


class TestCheckAllPermissions:
    """Tests para la función check_all_permissions."""
    
    def test_has_all_permissions_passes(self):
        """Tener todos los permisos no lanza excepción."""
        try:
            check_all_permissions("client", [
                Permission.EMERGENCY_CREATE,
                Permission.VEHICLE_CREATE,
                Permission.PROFILE_VIEW_OWN,
            ])
        except HTTPException:
            pytest.fail("No debería lanzar excepción si tiene todos")
    
    def test_missing_one_permission_raises(self):
        """Faltar un permiso lanza HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            check_all_permissions("client", [
                Permission.EMERGENCY_CREATE,  # Tiene este
                Permission.ADMIN_MANAGE_USERS,  # No tiene este
            ])
        
        assert exc_info.value.status_code == 403
        assert "Faltan" in exc_info.value.detail


class TestGetUserPermissionsList:
    """Tests para la función get_user_permissions_list."""
    
    def test_client_permissions_list(self):
        """Lista de permisos de cliente."""
        perms = get_user_permissions_list("client")
        
        assert isinstance(perms, list)
        assert len(perms) > 0
        assert "emergency:create" in perms
        assert "vehicle:create" in perms
        assert "admin:manage_users" not in perms
    
    def test_admin_permissions_list(self):
        """Lista de permisos de administrador."""
        perms = get_user_permissions_list("administrator")
        
        assert isinstance(perms, list)
        assert len(perms) > 0
        assert "admin:manage_users" in perms
        assert "admin:configure_system" in perms
    
    def test_invalid_role_returns_empty(self):
        """Rol inválido retorna lista vacía."""
        perms = get_user_permissions_list("invalid_role")
        assert perms == []


class TestUseCaseMapping:
    """Tests para verificar mapeo de casos de uso a permisos."""
    
    def test_cu03_reportar_emergencia(self):
        """CU03: Solo clientes pueden reportar emergencias."""
        assert has_permission(UserRole.CLIENT, Permission.EMERGENCY_CREATE)
        assert not has_permission(UserRole.WORKSHOP, Permission.EMERGENCY_CREATE)
        assert not has_permission(UserRole.TECHNICIAN, Permission.EMERGENCY_CREATE)
        assert not has_permission(UserRole.ADMINISTRATOR, Permission.EMERGENCY_CREATE)
    
    def test_cu07_gestionar_solicitudes(self):
        """CU07: Solo talleres pueden gestionar solicitudes entrantes."""
        assert has_permission(UserRole.WORKSHOP, Permission.REQUEST_VIEW_INCOMING)
        assert has_permission(UserRole.WORKSHOP, Permission.REQUEST_ACCEPT)
        assert not has_permission(UserRole.CLIENT, Permission.REQUEST_ACCEPT)
        assert not has_permission(UserRole.TECHNICIAN, Permission.REQUEST_ACCEPT)
    
    def test_cu08_gestionar_atencion(self):
        """CU08: Talleres y técnicos pueden gestionar atención."""
        # Taller puede asignar técnicos
        assert has_permission(UserRole.WORKSHOP, Permission.SERVICE_ASSIGN_TECHNICIAN)
        
        # Técnico NO puede asignar técnicos
        assert not has_permission(UserRole.TECHNICIAN, Permission.SERVICE_ASSIGN_TECHNICIAN)
        
        # Ambos pueden actualizar estado
        assert has_permission(UserRole.WORKSHOP, Permission.SERVICE_UPDATE_STATUS)
        assert has_permission(UserRole.TECHNICIAN, Permission.SERVICE_UPDATE_STATUS)
    
    def test_cu19_gestionar_tecnicos(self):
        """CU19: Solo talleres pueden gestionar técnicos."""
        assert has_permission(UserRole.WORKSHOP, Permission.TECHNICIAN_CREATE)
        assert has_permission(UserRole.WORKSHOP, Permission.TECHNICIAN_UPDATE)
        assert not has_permission(UserRole.TECHNICIAN, Permission.TECHNICIAN_CREATE)
        assert not has_permission(UserRole.CLIENT, Permission.TECHNICIAN_CREATE)
    
    def test_cu21_gestionar_usuarios(self):
        """CU21: Solo administradores pueden gestionar usuarios."""
        assert has_permission(UserRole.ADMINISTRATOR, Permission.ADMIN_MANAGE_USERS)
        assert not has_permission(UserRole.CLIENT, Permission.ADMIN_MANAGE_USERS)
        assert not has_permission(UserRole.WORKSHOP, Permission.ADMIN_MANAGE_USERS)
        assert not has_permission(UserRole.TECHNICIAN, Permission.ADMIN_MANAGE_USERS)
    
    def test_cu23_configurar_sistema(self):
        """CU23: Solo administradores pueden configurar sistema."""
        assert has_permission(UserRole.ADMINISTRATOR, Permission.ADMIN_CONFIGURE_SYSTEM)
        assert not has_permission(UserRole.CLIENT, Permission.ADMIN_CONFIGURE_SYSTEM)
        assert not has_permission(UserRole.WORKSHOP, Permission.ADMIN_CONFIGURE_SYSTEM)


class TestAuthenticationPermissions:
    """Tests para permisos de autenticación."""
    
    def test_all_users_can_login(self):
        """Todos los usuarios pueden hacer login."""
        for role in [UserRole.CLIENT, UserRole.WORKSHOP, UserRole.TECHNICIAN, UserRole.ADMINISTRATOR]:
            assert has_permission(role, Permission.AUTH_LOGIN)
            assert has_permission(role, Permission.AUTH_LOGOUT)
    
    def test_all_users_can_change_password(self):
        """Todos los usuarios pueden cambiar contraseña."""
        for role in [UserRole.CLIENT, UserRole.WORKSHOP, UserRole.TECHNICIAN, UserRole.ADMINISTRATOR]:
            assert has_permission(role, Permission.PASSWORD_CHANGE)
    
    def test_technician_cannot_register(self):
        """Técnicos no pueden auto-registrarse."""
        assert not has_permission(UserRole.TECHNICIAN, Permission.AUTH_REGISTER)
    
    def test_clients_can_register(self):
        """Clientes pueden auto-registrarse."""
        assert has_permission(UserRole.CLIENT, Permission.AUTH_REGISTER)


class TestProfilePermissions:
    """Tests para permisos de perfil."""
    
    def test_all_users_can_view_own_profile(self):
        """Todos los usuarios pueden ver su propio perfil."""
        for role in [UserRole.CLIENT, UserRole.WORKSHOP, UserRole.TECHNICIAN, UserRole.ADMINISTRATOR]:
            assert has_permission(role, Permission.PROFILE_VIEW_OWN)
    
    def test_all_users_can_update_own_profile(self):
        """Todos los usuarios pueden actualizar su propio perfil."""
        for role in [UserRole.CLIENT, UserRole.WORKSHOP, UserRole.TECHNICIAN, UserRole.ADMINISTRATOR]:
            assert has_permission(role, Permission.PROFILE_UPDATE_OWN)
    
    def test_only_client_can_delete_own_profile(self):
        """Solo clientes pueden eliminar su propio perfil."""
        assert has_permission(UserRole.CLIENT, Permission.PROFILE_DELETE_OWN)
        assert not has_permission(UserRole.WORKSHOP, Permission.PROFILE_DELETE_OWN)
        assert not has_permission(UserRole.TECHNICIAN, Permission.PROFILE_DELETE_OWN)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
