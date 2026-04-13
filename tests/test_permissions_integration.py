"""
Integration tests for the permissions system.

Tests authorization across different endpoints and user roles.
"""
import pytest
from fastapi import status
from httpx import AsyncClient

from app.core.permissions import UserRole, Permission
from app.core.security import create_access_token


class TestPermissionsIntegration:
    """Integration tests for permissions system."""
    
    @pytest.fixture
    def client_token(self):
        """Create access token for a client user."""
        return create_access_token(
            user_id=1,
            email="client@test.com",
            user_type=UserRole.CLIENT.value
        )
    
    @pytest.fixture
    def workshop_token(self):
        """Create access token for a workshop user."""
        return create_access_token(
            user_id=2,
            email="workshop@test.com",
            user_type=UserRole.WORKSHOP.value
        )
    
    @pytest.fixture
    def technician_token(self):
        """Create access token for a technician user."""
        return create_access_token(
            user_id=3,
            email="technician@test.com",
            user_type=UserRole.TECHNICIAN.value
        )
    
    @pytest.fixture
    def admin_token(self):
        """Create access token for an admin user."""
        return create_access_token(
            user_id=4,
            email="admin@test.com",
            user_type=UserRole.ADMINISTRATOR.value
        )
    
    # ==================== Profile Endpoints ====================
    
    @pytest.mark.asyncio
    async def test_get_profile_all_roles_allowed(
        self, async_client: AsyncClient, client_token, workshop_token, admin_token
    ):
        """Test that all authenticated users can view their own profile."""
        for token in [client_token, workshop_token, admin_token]:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            # May return 404 if user doesn't exist in DB, but should not be 403
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
    
    @pytest.mark.asyncio
    async def test_get_profile_without_token_forbidden(self, async_client: AsyncClient):
        """Test that unauthenticated users cannot view profile."""
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @pytest.mark.asyncio
    async def test_update_profile_all_roles_allowed(
        self, async_client: AsyncClient, client_token, workshop_token
    ):
        """Test that users can update their own profile."""
        for token in [client_token, workshop_token]:
            response = await async_client.patch(
                "/api/v1/auth/me",
                json={"direccion": "Nueva dirección"},
                headers={"Authorization": f"Bearer {token}"}
            )
            # May return 404 if user doesn't exist, but should not be 403
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]
    
    @pytest.mark.asyncio
    async def test_delete_profile_all_roles_allowed(
        self, async_client: AsyncClient, client_token
    ):
        """Test that users can delete their own account."""
        response = await async_client.delete(
            "/api/v1/auth/me",
            json={"password": "testpassword123"},
            headers={"Authorization": f"Bearer {client_token}"}
        )
        # May return 404 if user doesn't exist, but should not be 403
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_400_BAD_REQUEST
        ]
    
    # ==================== User Management Endpoints ====================
    
    @pytest.mark.asyncio
    async def test_list_users_admin_only(
        self, async_client: AsyncClient, admin_token, client_token
    ):
        """Test that only admins can list users."""
        # Admin should be allowed
        response = await async_client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Client should be forbidden
        response = await async_client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    # ==================== Audit Endpoints ====================
    
    @pytest.mark.asyncio
    async def test_view_audit_logs_admin_only(
        self, async_client: AsyncClient, admin_token, workshop_token
    ):
        """Test that only admins can view audit logs."""
        # Admin should be allowed
        response = await async_client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Workshop should be forbidden
        response = await async_client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {workshop_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @pytest.mark.asyncio
    async def test_view_user_activity_admin_only(
        self, async_client: AsyncClient, admin_token, client_token
    ):
        """Test that only admins can view user activity."""
        # Admin should be allowed
        response = await async_client.get(
            "/api/v1/audit/users/1/activity",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Client should be forbidden
        response = await async_client.get(
            "/api/v1/audit/users/1/activity",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @pytest.mark.asyncio
    async def test_cleanup_audit_logs_admin_only(
        self, async_client: AsyncClient, admin_token, workshop_token
    ):
        """Test that only admins can cleanup audit logs."""
        # Admin should be allowed
        response = await async_client.post(
            "/api/v1/audit/cleanup?days_to_keep=90",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Workshop should be forbidden
        response = await async_client.post(
            "/api/v1/audit/cleanup?days_to_keep=90",
            headers={"Authorization": f"Bearer {workshop_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    # ==================== Session Management ====================
    
    @pytest.mark.asyncio
    async def test_view_sessions_authenticated_users(
        self, async_client: AsyncClient, client_token, workshop_token
    ):
        """Test that authenticated users can view their own sessions."""
        for token in [client_token, workshop_token]:
            response = await async_client.get(
                "/api/v1/sessions",
                headers={"Authorization": f"Bearer {token}"}
            )
            # May return 400 if JTI not found, but should not be 403
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_404_NOT_FOUND
            ]
    
    @pytest.mark.asyncio
    async def test_revoke_sessions_authenticated_users(
        self, async_client: AsyncClient, client_token
    ):
        """Test that authenticated users can revoke their own sessions."""
        response = await async_client.delete(
            "/api/v1/sessions",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        # May return 400 if JTI not found, but should not be 403
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST
        ]


class TestRoleBasedAccess:
    """Test role-based access control patterns."""
    
    @pytest.fixture
    def tokens_by_role(self):
        """Create tokens for all roles."""
        return {
            UserRole.CLIENT: create_access_token(
                user_id=1, email="client@test.com", user_type=UserRole.CLIENT.value
            ),
            UserRole.WORKSHOP: create_access_token(
                user_id=2, email="workshop@test.com", user_type=UserRole.WORKSHOP.value
            ),
            UserRole.TECHNICIAN: create_access_token(
                user_id=3, email="tech@test.com", user_type=UserRole.TECHNICIAN.value
            ),
            UserRole.ADMINISTRATOR: create_access_token(
                user_id=4, email="admin@test.com", user_type=UserRole.ADMINISTRATOR.value
            ),
        }
    
    @pytest.mark.asyncio
    async def test_admin_endpoints_only_admin_access(
        self, async_client: AsyncClient, tokens_by_role
    ):
        """Test that admin endpoints are only accessible by administrators."""
        admin_endpoints = [
            ("GET", "/api/v1/users"),
            ("GET", "/api/v1/audit/logs"),
            ("POST", "/api/v1/audit/cleanup?days_to_keep=90"),
        ]
        
        for method, endpoint in admin_endpoints:
            # Admin should have access
            admin_response = await async_client.request(
                method,
                endpoint,
                headers={"Authorization": f"Bearer {tokens_by_role[UserRole.ADMINISTRATOR]}"}
            )
            assert admin_response.status_code != status.HTTP_403_FORBIDDEN, \
                f"Admin should have access to {method} {endpoint}"
            
            # Non-admin roles should be forbidden
            for role in [UserRole.CLIENT, UserRole.WORKSHOP, UserRole.TECHNICIAN]:
                response = await async_client.request(
                    method,
                    endpoint,
                    headers={"Authorization": f"Bearer {tokens_by_role[role]}"}
                )
                assert response.status_code == status.HTTP_403_FORBIDDEN, \
                    f"{role.value} should not have access to {method} {endpoint}"
    
    @pytest.mark.asyncio
    async def test_profile_endpoints_all_authenticated_users(
        self, async_client: AsyncClient, tokens_by_role
    ):
        """Test that profile endpoints are accessible by all authenticated users."""
        profile_endpoints = [
            ("GET", "/api/v1/auth/me"),
        ]
        
        for method, endpoint in profile_endpoints:
            for role, token in tokens_by_role.items():
                response = await async_client.request(
                    method,
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"}
                )
                # Should not be forbidden (may be 404 if user doesn't exist)
                assert response.status_code != status.HTTP_403_FORBIDDEN, \
                    f"{role.value} should have access to {method} {endpoint}"


class TestPermissionDenialMessages:
    """Test that permission denials return appropriate error messages."""
    
    @pytest.mark.asyncio
    async def test_permission_denial_returns_clear_message(
        self, async_client: AsyncClient
    ):
        """Test that permission denials include clear error messages."""
        client_token = create_access_token(
            user_id=1,
            email="client@test.com",
            user_type=UserRole.CLIENT.value
        )
        
        response = await async_client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "detail" in data or "error" in data
        # Should mention permission or authorization
        error_text = str(data).lower()
        assert any(word in error_text for word in ["permission", "forbidden", "authorized"])
    
    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, async_client: AsyncClient):
        """Test that missing authentication returns 401."""
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, async_client: AsyncClient):
        """Test that invalid tokens return 401."""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# Conftest fixtures for async client
@pytest.fixture
async def async_client():
    """Create async test client."""
    from httpx import AsyncClient
    from app.main import app
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
